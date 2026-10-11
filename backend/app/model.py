"""Architecture copied verbatim from final_fast.ipynb (so state_dict keys match),
plus a small Predictor wrapper used by the API."""
import threading
import warnings
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# The notebook calls torch.autocast(device_type="cuda", enabled=False) inside the FFT gate and
# decoder; on CPU-only machines that only emits a harmless warning.
warnings.filterwarnings("ignore", message=".*CUDA is not available.*")


class SpatioTemporalConv3D(nn.Module):
    def __init__(self, in_channels=7, embed_dim=64):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv3d(in_channels, 32, kernel_size=3, padding=1),
            nn.GroupNorm(num_groups=8, num_channels=32),
            nn.GELU(),
            nn.Conv3d(32, embed_dim, kernel_size=3, padding=1),
            nn.BatchNorm3d(embed_dim),
            nn.GELU())

    def forward(self, x):
        x = x.permute(0, 2, 1, 3, 4)
        x = self.conv(x)
        return x


class TemporalWindowAttention(nn.Module):
    def __init__(self, embed_dim=64, num_heads=4, window_size=4):
        super().__init__()
        self.window_size = window_size
        self.attention = nn.MultiheadAttention(embed_dim=embed_dim, num_heads=num_heads, batch_first=True)

    def forward(self, x):
        B, T, D = x.shape
        W = self.window_size
        pad_len = (W - T % W) % W
        if pad_len > 0:
            x = F.pad(x, (0, 0, 0, pad_len))
        Tp = x.shape[1]
        x = x.reshape(B, Tp // W, W, D)
        x = x.reshape(B * (Tp // W), W, D)
        attn_out, _ = self.attention(x, x, x)
        x = x + attn_out
        x = x.reshape(B, Tp, D)
        if pad_len > 0:
            x = x[:, :T]
        return x


class FFTFrequencyGate(nn.Module):
    def __init__(self, embed_dim=64, sequence_length=7):
        super().__init__()
        n_freq = sequence_length // 2 + 1
        self.gate = nn.Parameter(torch.ones(n_freq, embed_dim))

    def forward(self, x):
        in_dtype = x.dtype
        with torch.autocast(device_type="cuda", enabled=False):
            x = x.float()
            freq = torch.fft.rfft(x, dim=1)
            gate = torch.sigmoid(self.gate).unsqueeze(0)
            out = torch.fft.irfft(freq * gate, n=x.shape[1], dim=1)
        return out.to(in_dtype)


class FWinFormerBlock(nn.Module):
    def __init__(self, embed_dim=64, num_heads=4, window_size=4, sequence_length=7):
        super().__init__()
        self.local_cnn = nn.Sequential(
            nn.Conv1d(embed_dim, embed_dim, kernel_size=3, padding=1, groups=embed_dim),
            nn.GELU(),
            nn.Conv1d(embed_dim, embed_dim, kernel_size=1))
        self.window_attention = TemporalWindowAttention(embed_dim, num_heads, window_size)
        self.temporal_mixing = nn.Sequential(
            nn.Conv1d(embed_dim, embed_dim, kernel_size=3, padding=1, groups=embed_dim),
            nn.GELU(),
            nn.Conv1d(embed_dim, embed_dim, kernel_size=1))
        self.fft_gate = FFTFrequencyGate(embed_dim, sequence_length)
        self.norm1 = nn.LayerNorm(embed_dim)
        self.norm2 = nn.LayerNorm(embed_dim)
        self.norm3 = nn.LayerNorm(embed_dim)
        self.norm4 = nn.LayerNorm(embed_dim)

    def forward(self, x):
        residual = x
        x_cnn = self.local_cnn(x.transpose(1, 2)).transpose(1, 2)
        x = self.norm1(residual + x_cnn)

        residual = x
        x_attn = self.window_attention(x)
        x = self.norm2(residual + x_attn)

        residual = x
        x_temp = self.temporal_mixing(x.transpose(1, 2)).transpose(1, 2)
        x = self.norm3(residual + x_temp)

        residual = x
        x_fft = self.fft_gate(x)
        x = self.norm4(residual + x_fft)
        return x


class ResidualDepthDecoder(nn.Module):
    def __init__(self, embed_dim=64, n_depths=15, depth_dim=16):
        super().__init__()
        self.n_depths = n_depths
        self.depth_embedding = nn.Parameter(torch.randn(n_depths, depth_dim) * 0.02)
        self.clim_encoder = nn.Sequential(nn.Linear(1, 16), nn.GELU(), nn.Linear(16, 16))
        input_dim = embed_dim + depth_dim + 16
        self.decoder = nn.Sequential(
            nn.Linear(input_dim, 128), nn.GELU(), nn.Dropout(0.10),
            nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, ocean_latent, climatology):
        with torch.autocast(device_type="cuda", enabled=False):
            ocean_latent = ocean_latent.float()
            climatology = climatology.float()
            B = ocean_latent.shape[0]
            F_latent = ocean_latent.unsqueeze(1).expand(-1, self.n_depths, -1)
            depth_emb = self.depth_embedding.unsqueeze(0).expand(B, -1, -1)
            clim_emb = self.clim_encoder(climatology.unsqueeze(-1))
            decoder_input = torch.cat([F_latent, depth_emb, clim_emb], dim=-1)
            residual = self.decoder(decoder_input).squeeze(-1)
            temperature = climatology + residual
        return temperature, residual


class ThermoclineAwareOceanModel(nn.Module):
    def __init__(self, in_channels=7, n_depths=15, embed_dim=64, temporal_window=7):
        super().__init__()
        self.st_encoder = SpatioTemporalConv3D(in_channels=in_channels, embed_dim=embed_dim)
        self.fwinformer = FWinFormerBlock(embed_dim=embed_dim, num_heads=4, window_size=4,
                                          sequence_length=temporal_window)
        self.decoder = ResidualDepthDecoder(embed_dim=embed_dim, n_depths=n_depths, depth_dim=16)

    def forward(self, x, climatology):
        features = self.st_encoder(x)               # B x 64 x T x H x W
        features = features.mean(dim=(-1, -2))      # B x 64 x T
        features = features.transpose(1, 2)         # B x T x 64
        temporal_features = self.fwinformer(features)
        ocean_latent = temporal_features.mean(dim=1)
        temperature, residual = self.decoder(ocean_latent, climatology)
        return temperature, residual, ocean_latent


class Predictor:
    """Loads weights + climatology once; thread-safe inference on numpy arrays."""

    def __init__(self, artifacts_dir: Path, device: str = "auto", batch_size: int = 1024):
        artifacts_dir = Path(artifacts_dir)
        self.device = torch.device("cuda" if (device == "auto" and torch.cuda.is_available())
                                   else ("cpu" if device == "auto" else device))
        self.use_amp = self.device.type == "cuda"      # same bf16 autocast as training/eval
        self.batch_size = batch_size
        self._lock = threading.Lock()

        self._clim = np.load(artifacts_dir / "monthly_clim.npy", mmap_mode="r")
        if self._clim.ndim != 4 or self._clim.shape[0] != 12:
            raise ValueError(f"monthly_clim.npy must be [12, depth, lat, lon]; got {self._clim.shape}")

        self.model = ThermoclineAwareOceanModel(in_channels=7, n_depths=15, embed_dim=64,
                                                temporal_window=7).to(self.device)
        state = torch.load(artifacts_dir / "best_thermocline_model.pt",
                           map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()

    def climatology(self, month: int, la: np.ndarray, lo: np.ndarray) -> np.ndarray:
        """[B, depth] climatology for the 1-based month (NaN over land / masked points)."""
        return np.asarray(self._clim[month - 1][:, la, lo]).T.astype(np.float32)

    @torch.inference_mode()
    def predict(self, x: np.ndarray, clim: np.ndarray):
        """x [B,T,V,5,5] float32, clim [B,depth] -> (temperature, residual), each [B,depth] float32."""
        temps, resids = [], []
        with self._lock:
            for i in range(0, len(x), self.batch_size):
                xb = torch.from_numpy(x[i:i + self.batch_size]).to(self.device)
                cb = torch.from_numpy(clim[i:i + self.batch_size]).to(self.device)
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=self.use_amp):
                    t, r, _ = self.model(xb, cb)
                temps.append(t.float().cpu().numpy())
                resids.append(r.float().cpu().numpy())
        return np.concatenate(temps), np.concatenate(resids)
