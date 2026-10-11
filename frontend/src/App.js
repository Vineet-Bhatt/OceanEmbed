import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

window.ASSET_PREFIX = '';
window.SCRIPT_PREFIX = '';
window.SCENE_PATH = '2509662.json';
window.CONTEXT_OPTIONS = {
  antialias: true,
  alpha: false,
  preserveDrawingBuffer: false,
  deviceTypes: ['webgl2', 'webgl1'],
  powerPreference: 'high-performance'
};
window.SCRIPTS = [
  292211860, 292242166, 296433599, 292242168, 292242169, 292242204,
  292242205, 292242206, 292242209, 292280431, 292242250, 292242262,
  292242417, 292242420, 292242465, 292242469, 292280661, 292432194,
  292438594, 292439810, 292447614, 292449081, 292490275, 292578861,
  292601043, 292617818, 292624780, 293798294, 293808903, 294125708,
  294129713, 294207062, 294368960, 294466898, 294724770, 294753048,
  294754040, 294755262, 294760515, 294761465, 295516297, 295593207,
  295593211, 295595875, 295638209, 295642651, 295659089, 295897434,
  295912295, 295912296, 295953003, 296018586, 296215328, 296312491,
  296343035, 296362305, 296407558, 296436897, 296475080, 296495520,
  296574674, 296654444, 296663079, 296783254, 296791673, 297063124,
  297128009, 297174797, 297185569, 297199958, 297205581, 297255727,
  297273798, 297281639, 297301043, 297329227, 297335929, 297382047,
  297385086, 297417320, 297435347, 297458955, 297470913, 297624079,
  297624710, 297695678, 297734634, 297775167, 297926489, 298051497,
  298146151, 298204720, 298215984, 298281233, 298281707, 298346278,
  298361492, 298371763, 298497886, 298537756, 298616193, 298667245,
  298739098, 298850929, 299037872
];
window.CONFIG_FILENAME = 'config.json';
window.INPUT_SETTINGS = {
  useKeyboard: true,
  useMouse: true,
  useGamepads: false,
  useTouch: true
};
pc.script.legacy = false;
window.PRELOAD_MODULES = [{
  moduleName: 'BASIS',
  glueUrl: 'files/assets/298861850/1/basis.wasm.js',
  wasmUrl: 'files/assets/298861848/1/basis.wasm.wasm',
  fallbackUrl: 'files/assets/298861849/1/basis.js',
  preload: false
}];

var loadModules = function (modules, urlPrefix, doneCallback) {
  if (!modules || modules.length === 0) {
    setTimeout(doneCallback);
    return;
  }

  var remainingModules = modules.length;
  var onModuleLoaded = function () {
    remainingModules--;
    if (remainingModules === 0) doneCallback();
  };

  modules.forEach(function (module) {
    pc.WasmModule.setConfig(module.moduleName, {
      glueUrl: urlPrefix + module.glueUrl,
      wasmUrl: urlPrefix + module.wasmUrl,
      fallbackUrl: urlPrefix + module.fallbackUrl
    });

    if (Object.prototype.hasOwnProperty.call(module, 'preload') && !module.preload) {
      onModuleLoaded();
    } else if (module.moduleName === 'BASIS') {
      pc.basisInitialize();
      onModuleLoaded();
    } else if (module.moduleName === 'DracoDecoderModule' && pc.dracoInitialize) {
      pc.dracoInitialize();
      onModuleLoaded();
    } else {
      pc.WasmModule.getInstance(module.moduleName, onModuleLoaded);
    }
  });
};

window.loadModules = loadModules;

(function () {
  var canvasId = 'application-canvas';
  var lastWindowHeight = window.innerHeight;
  var lastWindowWidth = window.innerWidth;
  var resizePoll = null;

  function getIosVersion() {
    if (!/iP(hone|od|ad)/.test(navigator.platform)) return null;
    var version = navigator.appVersion.match(/OS (\d+)_(\d+)_?(\d+)?/);
    return [
      parseInt(version[1], 10),
      parseInt(version[2], 10),
      parseInt(version[3] || 0, 10)
    ];
  }

  var iosVersion = getIosVersion();

  function createCanvas() {
    var canvas = document.createElement('canvas');
    canvas.id = canvasId;
    canvas.tabIndex = 0;
    canvas.onselectstart = function () { return false; };
    canvas.style.webkitUserSelect = 'none';
    document.body.appendChild(canvas);
    return canvas;
  }

  function resizeCanvas(app, canvas) {
    canvas.style.width = '';
    canvas.style.height = '';
    app.resizeCanvas(canvas.width, canvas.height);

    var fillMode = app._fillMode;
    if (fillMode === pc.FILLMODE_NONE || fillMode === pc.FILLMODE_KEEP_ASPECT) {
      if ((fillMode === pc.FILLMODE_NONE && canvas.clientHeight < window.innerHeight) ||
        (canvas.clientWidth / canvas.clientHeight >= window.innerWidth / window.innerHeight)) {
        canvas.style.marginTop = Math.floor((window.innerHeight - canvas.clientHeight) / 2) + 'px';
      } else {
        canvas.style.marginTop = '';
      }
    }

    lastWindowHeight = window.innerHeight;
    lastWindowWidth = window.innerWidth;
    if (iosVersion && iosVersion[0] <= 12) window.scrollTo(0, 0);
  }

  function reflow(app, canvas) {
    resizeCanvas(app, canvas);
    if (resizePoll !== null) return;

    resizePoll = window.setInterval(function () {
      if (lastWindowHeight !== window.innerHeight || lastWindowWidth !== window.innerWidth) {
        resizeCanvas(app, canvas);
      }
    }, 100);

    window.setTimeout(function () {
      window.clearInterval(resizePoll);
      resizePoll = null;
    }, 2000);
  }

  function showError(message) {
    var element = document.createElement('div');
    element.textContent = 'Could not initialize application. Error: ' + message;
    element.style.cssText = 'position:fixed;inset:0;display:grid;place-items:center;background:#8CE;color:#000';
    document.body.appendChild(element);
  }

  function createGraphicsDevice(canvas, callback) {
    var options = window.CONTEXT_OPTIONS || {};
    var deviceTypes = (options.deviceTypes || []).concat('webgl');
    var assetPrefix = window.ASSET_PREFIX ? window.ASSET_PREFIX.replace(/\/$/g, '') + '/' : '';

    if (typeof window.Promise === 'function') {
      pc.createGraphicsDevice(canvas, {
        deviceTypes: deviceTypes,
        glslangUrl: assetPrefix + 'glslang.js',
        twgslUrl: assetPrefix + 'twgsl.js',
        powerPreference: options.powerPreference,
        antialias: options.antialias !== false,
        alpha: options.alpha === true,
        preserveDrawingBuffer: !!options.preserveDrawingBuffer
      }).then(callback).catch(function (error) {
        console.error('Device creation error:', error);
        callback(null);
      });
      return;
    }

    var webgl1Index = deviceTypes.indexOf('webgl1');
    var webgl2Index = deviceTypes.indexOf('webgl2');
    var legacyOptions = {
      powerPreference: options.powerPreference,
      antialias: options.antialias !== false,
      alpha: options.transparentCanvas !== false,
      preserveDrawingBuffer: !!options.preserveDrawingBuffer,
      preferWebGl2: webgl2Index > webgl1Index
    };
    if (pc.platform.browser && navigator.xr) legacyOptions.xrCompatible = true;
    callback(new pc.WebglGraphicsDevice(canvas, legacyOptions));
  }

  function createApplication(canvas, device) {
    var app = new pc.AppBase(canvas);
    window.__oceanEmbedApp = app;

    var options = new pc.AppOptions();
    options.graphicsDevice = device;
    options.componentSystems = [
      pc.RigidBodyComponentSystem, pc.CollisionComponentSystem, pc.JointComponentSystem,
      pc.AnimationComponentSystem, pc.AnimComponentSystem, pc.ModelComponentSystem,
      pc.RenderComponentSystem, pc.CameraComponentSystem, pc.LightComponentSystem,
      pc.script.legacy ? pc.ScriptLegacyComponentSystem : pc.ScriptComponentSystem,
      pc.ParticleSystemComponentSystem, pc.ScreenComponentSystem, pc.ElementComponentSystem,
      pc.ButtonComponentSystem, pc.ScrollViewComponentSystem, pc.ScrollbarComponentSystem,
      pc.SpriteComponentSystem, pc.LayoutGroupComponentSystem, pc.LayoutChildComponentSystem,
      pc.ZoneComponentSystem, pc.GSplatComponentSystem
    ].filter(Boolean);
    options.resourceHandlers = [
      pc.RenderHandler, pc.AnimationHandler, pc.AnimClipHandler, pc.AnimStateGraphHandler,
      pc.ModelHandler, pc.MaterialHandler, pc.TextureHandler, pc.TextHandler, pc.JsonHandler,
      pc.ScriptHandler, pc.SceneHandler, pc.CubemapHandler, pc.HtmlHandler,
      pc.CssHandler, pc.ShaderHandler, pc.HierarchyHandler, pc.FolderHandler, pc.FontHandler,
      pc.BinaryHandler, pc.TextureAtlasHandler, pc.SpriteHandler, pc.TemplateHandler,
      pc.ContainerHandler, pc.GSplatHandler
    ].filter(Boolean);
    options.elementInput = new pc.ElementInput(canvas, {
      useMouse: window.INPUT_SETTINGS.useMouse,
      useTouch: window.INPUT_SETTINGS.useTouch
    });
    options.keyboard = window.INPUT_SETTINGS.useKeyboard ? new pc.Keyboard(window) : null;
    options.mouse = window.INPUT_SETTINGS.useMouse ? new pc.Mouse(canvas) : null;
    options.gamepads = window.INPUT_SETTINGS.useGamepads ? new pc.GamePads() : null;
    options.touch = window.INPUT_SETTINGS.useTouch && pc.platform.touch ?
      new pc.TouchDevice(canvas) : null;
    options.assetPrefix = window.ASSET_PREFIX || '';
    options.scriptPrefix = window.SCRIPT_PREFIX || '';
    options.scriptsOrder = window.SCRIPTS || [];
    options.lightmapper = pc.Lightmapper;
    options.batchManager = pc.BatchManager;
    options.xr = pc.XrManager;

    try {
      app.init(options);
    } catch (error) {
      showError(error);
      console.error(error);
      return null;
    }
    return app;
  }

  function configureApplication(app, canvas) {
    app.configure(window.CONFIG_FILENAME, function (error) {
      if (error) {
        console.error(error);
        return;
      }

      var style = document.head.querySelector('style');
      if (style) {
        style.innerHTML += '@media screen and (min-aspect-ratio: ' +
          app._width + '/' + app._height + ') {' +
          '#application-canvas.fill-mode-KEEP_ASPECT {' +
          'width:auto;height:100%;margin:0 auto;}}';
      }
      canvas.classList.add('fill-mode-' + app.fillMode);

      window.setTimeout(function () {
        reflow(app, canvas);
        var handleResize = function () { reflow(app, canvas); };
        window.addEventListener('resize', handleResize, false);
        window.addEventListener('orientationchange', handleResize, false);
        app.preload(function () {
          app.scenes.loadScene(window.SCENE_PATH, function (sceneError) {
            if (sceneError) {
              console.error(sceneError);
              return;
            }
            app.start();
          });
        });
      });
    });
  }

  var canvas = createCanvas();
  createGraphicsDevice(canvas, function (device) {
    if (!device) return;

    var app = createApplication(canvas, device);
    if (!app) return;

    loadModules(window.PRELOAD_MODULES, window.ASSET_PREFIX, function () {
      configureApplication(app, canvas);
    });
  });
}());

(function () {
  var STUDY_AREA_BOUNDS = [[5, 45], [30, 105]];
  var PANEL_MATERIAL_NAMES = ['Solar_panel', 'black'];
  var SCENE_WAIT_INTERVAL_MS = 250;
  var MAX_SCENE_ATTEMPTS = 120;
  var SATELLITE_HORIZONTAL_OFFSET = 0.95;
  var SATELLITE_SCROLL_TRAVEL = 8;

  function hideOtherScenes(root, satelliteScene) {
    var sceneRoot = root.findByName('Root') || root;
    sceneRoot.children.forEach(function (entity) {
      if (entity.name.indexOf('scene') === 0 && entity !== satelliteScene) {
        entity.enabled = false;
      }
    });
    satelliteScene.enabled = true;
  }

  function prepareCamera(root) {
    var camera = root.findByName('Camera');
    if (camera && camera.script && camera.script.cameraController) {
      camera.script.cameraController.enabled = false;
    }
  }

  function startSatelliteDeployment(satellite) {
    var mover = satellite && satellite.script && satellite.script.satelliteMover;
    if (!mover) {
      console.error('Could not find the satellite motion controller.');
      return;
    }

    mover._kfs.forEach(function (keyframe) {
      keyframe.pos.x += SATELLITE_HORIZONTAL_OFFSET;
    });
    mover._state = 'scrolling';
    mover._progress = 0;
    mover.lerpSpeed = 1;
    mover._computeTarget();
    mover._curOffset.copy(mover._tgtOffset);
    mover._curRot.copy(mover._tgtRot);
    mover._applyWorld();
    mover._playDeploy();

    var startingPosition = satellite.getLocalPosition().clone();
    mover.enabled = false;
    var mouseParallax = satellite.script.mouseParallax;
    if (mouseParallax) mouseParallax.enabled = false;

    var hero = document.getElementById('earth-hero');
    var frameRequested = false;
    function updateSatelliteForScroll() {
      frameRequested = false;
      var progress = Math.min(window.scrollY / Math.max(hero.offsetHeight * 0.75, 1), 1);
      satellite.setLocalPosition(
        startingPosition.x,
        startingPosition.y + SATELLITE_SCROLL_TRAVEL * progress,
        startingPosition.z
      );
    }
    function requestScrollUpdate() {
      if (frameRequested) return;
      frameRequested = true;
      window.requestAnimationFrame(updateSatelliteForScroll);
    }

    window.addEventListener('scroll', requestScrollUpdate, { passive: true });
    window.addEventListener('resize', requestScrollUpdate);
    requestScrollUpdate();
  }

  function createPanelTexture(app) {
    var canvas = document.createElement('canvas');
    canvas.width = canvas.height = 512;
    var context = canvas.getContext('2d');
    if (!context) {
      console.error('Could not create the solar-panel texture.');
      return null;
    }

    var cellCount = 8;
    var cellSize = canvas.width / cellCount;
    context.fillStyle = '#101a2b';
    context.fillRect(0, 0, canvas.width, canvas.height);

    for (var row = 0; row < cellCount; row++) {
      for (var column = 0; column < cellCount; column++) {
        var shade = (row * 7 + column * 11) % 14;
        context.fillStyle = 'rgb(' + (15 + shade) + ',' +
          (31 + shade) + ',' + (57 + shade * 2) + ')';
        context.fillRect(
          column * cellSize + 2,
          row * cellSize + 2,
          cellSize - 4,
          cellSize - 4
        );
      }
    }

    context.strokeStyle = 'rgba(150, 190, 229, 0.9)';
    context.lineWidth = 2;
    for (var line = 0; line <= cellCount; line++) {
      context.beginPath();
      context.moveTo(line * cellSize, 0);
      context.lineTo(line * cellSize, canvas.height);
      context.stroke();
      context.beginPath();
      context.moveTo(0, line * cellSize);
      context.lineTo(canvas.width, line * cellSize);
      context.stroke();
    }

    var texture = new pc.Texture(app.graphicsDevice, {
      width: canvas.width,
      height: canvas.height,
      format: pc.PIXELFORMAT_R8_G8_B8_A8,
      mipmaps: true
    });
    texture.setSource(canvas);
    texture.addressU = pc.ADDRESS_REPEAT;
    texture.addressV = pc.ADDRESS_REPEAT;
    texture.minFilter = pc.FILTER_LINEAR_MIPMAP_LINEAR;
    texture.magFilter = pc.FILTER_LINEAR;
    return texture;
  }

  function applyPanelTexture(satellite, app) {
    var dataScan = satellite && satellite.script && satellite.script.dataScan;
    if (!dataScan || !window.pc) return;

    var texture = createPanelTexture(app);
    if (!texture) return;

    dataScan._slots.forEach(function (slot) {
      if (PANEL_MATERIAL_NAMES.indexOf(slot.original.name) === -1) return;
      [slot.original, slot.clone].forEach(function (material) {
        material.diffuseMap = texture;
        material.diffuse = new pc.Color(1, 1, 1);
        material.metalness = 0.65;
        material.update();
      });
    });
  }

  function disableUnusedInterface(root, satellite) {
    var label = satellite && satellite.script && satellite.script.satelliteLabel;
    if (label) label.enabled = false;

    var managers = root.findByName('Managers');
    if (managers) managers.enabled = false;

    var uiCamera = root.findByName('UICamera ');
    if (uiCamera) uiCamera.enabled = false;

    ['TransitionSatellite', 'TransitionMap', 'TransitionQuantum'].forEach(function (name) {
      var transition = root.findByName(name);
      if (transition) transition.enabled = false;
    });
  }

  function initializeSatellitePage(app, root, satelliteScene) {
    hideOtherScenes(root, satelliteScene);
    prepareCamera(root);

    var satellite = satelliteScene.findByName('StarlinkV2-1');
    startSatelliteDeployment(satellite);
    applyPanelTexture(satellite, app);
    disableUnusedInterface(root, satellite);
  }

  function waitForSatelliteScene() {
    var attempts = 0;
    var timer = window.setInterval(function () {
      var app = window.__oceanEmbedApp;
      var root = app && app.root;
      var satelliteScene = root && root.findByName('sceneSatellite');

      if (satelliteScene) {
        window.clearInterval(timer);
        initializeSatellitePage(app, root, satelliteScene);
      } else if (++attempts > MAX_SCENE_ATTEMPTS) {
        window.clearInterval(timer);
        console.error('Could not find the satellite scene in the PlayCanvas app.');
      }
    }, SCENE_WAIT_INTERVAL_MS);
  }

  function initializeStudyMap() {
    var mapElement = document.getElementById('location-map');
    var latitudeInput = document.getElementById('latitude');
    var longitudeInput = document.getElementById('longitude');
    if (!mapElement || !latitudeInput || !longitudeInput) return null;

    var bounds = L.latLngBounds(STUDY_AREA_BOUNDS);
    var map = L.map(mapElement, {
      scrollWheelZoom: true,
      maxBounds: bounds,
      maxBoundsViscosity: 1,
      zoomSnap: 0.1,
      attributionControl: false,
    });
    L.tileLayer('https://{s}.google.com/vt/lyrs=p&x={x}&y={y}&z={z}', {
      maxZoom: 12,
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3']
    }).addTo(map);

    L.rectangle(bounds, {
      color: '#ffffff',
      weight: 1.5,
      opacity: 0.58,
      fillColor: '#ffffff',
      fillOpacity: 0.025,
      dashArray: '6 5',
      interactive: false
    }).addTo(map);

    var marker = L.circleMarker([
      Number(latitudeInput.value),
      Number(longitudeInput.value)
    ], {
      radius: 5,
      color: '#06171d',
      weight: 2,
      fillColor: '#808080',
      fillOpacity: 1
    }).addTo(map);

    var mapStatus = document.getElementById('map-status');
    var landGeoJSON = null;
    if (mapStatus) mapStatus.textContent = 'Loading land boundaries…';

    function pointInRing(longitude, latitude, ring) {
      var inside = false;
      for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        var current = ring[i];
        var previous = ring[j];
        var cross = (longitude - previous[0]) * (current[1] - previous[1]) -
          (latitude - previous[1]) * (current[0] - previous[0]);
        var onSegment = Math.abs(cross) < 1e-8 &&
          longitude >= Math.min(previous[0], current[0]) - 1e-8 &&
          longitude <= Math.max(previous[0], current[0]) + 1e-8 &&
          latitude >= Math.min(previous[1], current[1]) - 1e-8 &&
          latitude <= Math.max(previous[1], current[1]) + 1e-8;
        if (onSegment) return true;
        var crossesLatitude = (current[1] > latitude) !== (previous[1] > latitude);
        if (crossesLatitude &&
          longitude < (previous[0] - current[0]) *
          (latitude - current[1]) / (previous[1] - current[1]) + current[0]) {
          inside = !inside;
        }
      }
      return inside;
    }

    function isLandPoint(latitude, longitude) {
      return landGeoJSON.features.some(function (feature) {
        var geometry = feature.geometry;
        var polygons = geometry.type === 'Polygon'
          ? [geometry.coordinates]
          : geometry.coordinates;
        return polygons.some(function (polygon) {
          return pointInRing(longitude, latitude, polygon[0]) &&
            !polygon.slice(1).some(function (hole) {
              return pointInRing(longitude, latitude, hole);
            });
        });
      });
    }

    fetch('/custom.geo.json')
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Land boundary request failed (' + response.status + ').');
        }
        return response.json();
      })
      .then(function (data) {
        if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) ||
          data.features.length === 0 || data.features.some(function (feature) {
            return !feature || !feature.geometry ||
              ['Polygon', 'MultiPolygon'].indexOf(feature.geometry.type) === -1;
          })) {
          throw new Error('The land boundary data is invalid.');
        }
        landGeoJSON = data;
        if (mapStatus) mapStatus.textContent = 'Select an ocean point on the map.';
      })
      .catch(function (error) {
        console.error('Failed to load land boundaries:', error);
        if (mapStatus) mapStatus.textContent = 'Land boundaries are unavailable. Enter coordinates manually.';
      });

    function updateMarker() {
      var latitude = Number(latitudeInput.value);
      var longitude = Number(longitudeInput.value);
      if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
        marker.setLatLng([latitude, longitude]);

        var latStr = Math.abs(latitude).toFixed(latitude % 1 === 0 ? 0 : 2) + '°' + (latitude >= 0 ? 'N' : 'S');
        var lngStr = Math.abs(longitude).toFixed(longitude % 1 === 0 ? 0 : 2) + '°' + (longitude >= 0 ? 'E' : 'W');
        var coordStr = latStr + ' \u00A0 ' + lngStr;

        var heroCoord = document.querySelector('.hero-coordinate');
        if (heroCoord) heroCoord.innerHTML = coordStr;
      }
    }

    function snapToGrid(value) {
      return Math.round(value * 4) / 4;
    }

    map.on('click', function (event) {
      if (!bounds.contains(event.latlng)) return;
      if (!landGeoJSON) {
        if (mapStatus) mapStatus.textContent = 'Land boundaries are still loading. Please enter coordinates manually.';
        return;
      }

      var snappedLat = snapToGrid(event.latlng.lat);
      var snappedLng = snapToGrid(event.latlng.lng);

      if (isLandPoint(snappedLat, snappedLng)) {
        if (mapStatus) mapStatus.textContent = 'That point is on land. Choose a point in the ocean.';
        return;
      }

      latitudeInput.value = snappedLat.toFixed(2);
      longitudeInput.value = snappedLng.toFixed(2);
      updateMarker();
      if (mapStatus) mapStatus.textContent = 'Ocean location selected.';
    });
    updateMarker();

    latitudeInput.addEventListener('input', updateMarker);
    longitudeInput.addEventListener('input', updateMarker);
    return map;
  }

  function initializePredictionForm() {
  var form = document.getElementById('prediction-form');
  if (!form) return;

  var modal = document.getElementById('prediction-modal');
  var openButton = document.getElementById('scroll-cue');
  var cancelButton = document.getElementById('cancel-prediction');
  var todayButton = document.getElementById('today-button');
  var studyMap = initializeStudyMap();
  var dateInput = document.getElementById('target-date');
  var status = document.getElementById('prediction-status');
  var button = document.getElementById('predict-button');
  var result = document.getElementById('prediction-result');
  var modalCloseTimer = null;

  function closeModal() {
    if (!modal || !modal.open || modalCloseTimer !== null) return;

    modal.classList.add('is-closing');
    var prefersReducedMotion = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var exitDuration = prefersReducedMotion ? 0 : 800;
    modalCloseTimer = window.setTimeout(function () {
      modal.close();
      modal.classList.remove('is-closing');
      modalCloseTimer = null;
    }, exitDuration);
  }

  function openModal() {
    if (!modal) return;
    if (modalCloseTimer !== null) {
      window.clearTimeout(modalCloseTimer);
      modalCloseTimer = null;
      modal.classList.remove('is-closing');
    }
    if (modal.open) return;
    modal.showModal();
    window.requestAnimationFrame(function () {
      if (studyMap) {
        studyMap.invalidateSize();
        studyMap.fitBounds(STUDY_AREA_BOUNDS, {
          padding: [6, 6],
          animate: false
        });
      }
      form.elements.latitude.focus();
    });
  }

  if (openButton && modal) {
    openButton.addEventListener('click', openModal);
  }
  if (cancelButton && modal) {
    cancelButton.addEventListener('click', closeModal);
  }
  if (modal) {
    modal.addEventListener('click', function (event) {
      if (event.target === modal) closeModal();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && modal.open) {
        event.preventDefault();
        closeModal();
      }
    });
    modal.addEventListener('cancel', function (event) {
      event.preventDefault();
      closeModal();
    });
  }

  function getTodayDateValue() {
    var today = new Date();
    return [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0')
    ].join('-');
  }

  dateInput.value = getTodayDateValue();
  if (todayButton) {
    todayButton.addEventListener('click', function () {
      dateInput.value = getTodayDateValue();
      dateInput.dispatchEvent(new Event('change', { bubbles: true }));
      dateInput.focus();
    });
  }

  var query = new URLSearchParams(window.location.search);
  ['latitude', 'longitude', 'date'].forEach(function (name) {
    var value = query.get(name);
    if (value && form.elements[name]) form.elements[name].value = value;
  });
  form.elements.latitude.dispatchEvent(new Event('input'));
  form.elements.longitude.dispatchEvent(new Event('input'));

  function showResult(body, requestedDate) {
    var profile = body.temperature_profile || body.profile || {};
    var rows = Array.isArray(profile)
      ? profile.map(function (point) {
        return point && Array.isArray(point)
          ? [point[0], point[1]]
          : [point && point.depth_m, point && point.temperature_c];
      })
      : profile && typeof profile === 'object'
        ? Object.entries(profile).map(function (entry) {
          return [parseFloat(entry[0]), entry[1]];
        })
        : [];
    rows = rows.filter(function (point) {
      return Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]));
    }).sort(function (a, b) {
      return Number(a[0]) - Number(b[0]);
    });
    if (!rows.length) {
      throw new Error('The prediction service returned no temperature profile.');
    }

    result.replaceChildren();

    var closeButton = document.createElement('button');
    closeButton.className = 'result-close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', 'Close prediction results');
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', function () {
      result.hidden = true;
    });

    var heading = document.createElement('h3');
    heading.textContent = 'Subsurface temperature profile';
    var location = document.createElement('p');
    var latitude = body.target_latitude ?? body.latitude ?? form.elements.latitude.value;
    var longitude = body.target_longitude ?? body.longitude ?? form.elements.longitude.value;
    location.className = 'result-location';
    location.textContent = Number(latitude).toFixed(2) + '°N, ' +
      Number(longitude).toFixed(2) + '°E · ' + (body.timestamp || body.date || requestedDate);

    var table = document.createElement('div');
    table.className = 'profile-table';
    var header = document.createElement('div');
    header.className = 'profile-row profile-head';
    header.innerHTML = '<span>Depth (m)</span><span>Temperature (°C)</span>';
    table.appendChild(header);
    rows.forEach(function (point) {
      var row = document.createElement('div');
      row.className = 'profile-row';
      var depth = document.createElement('span');
      depth.textContent = point[0];
      var temperature = document.createElement('span');
      temperature.textContent = Number(point[1]).toFixed(2);
      row.append(depth, temperature);
      table.appendChild(row);
    });

    result.append(closeButton, heading, location, table);
    result.hidden = false;
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (!form.reportValidity()) return;

    var requestedDate = dateInput.value;
    status.textContent = 'Requesting temperature profile…';
    status.removeAttribute('data-error');
    button.disabled = true;
    result.hidden = true;

    try {
      var apiUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
      var response = await fetch(apiUrl + '/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          latitude: Number(form.elements.latitude.value),
          longitude: Number(form.elements.longitude.value),
          date: requestedDate
        })
      });
      var responseText = await response.text();
      var body;
      try {
        body = JSON.parse(responseText);
      } catch {
        if (!response.ok) {
          throw new Error('Prediction request failed (' + response.status + ').');
        }
        throw new Error('The prediction service returned an invalid response.');
      }
      if (!response.ok) {
        throw new Error(body && body.detail || 'Prediction request failed (' + response.status + ').');
      }
      if (!body || typeof body !== 'object') {
        throw new Error('The prediction service returned an invalid response.');
      }
      showResult(body, requestedDate);
      status.textContent = 'Prediction received.';
      if (modal && modal.open) closeModal();
      window.setTimeout(function () {
        result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 0);
    } catch (error) {
      status.textContent = error.message === 'Failed to fetch'
        ? 'Could not reach the prediction service. Start the API server and try again.'
        : error.message;
      status.setAttribute('data-error', 'true');
    } finally {
      button.disabled = false;
    }
  });
}

initializePredictionForm();
waitForSatelliteScene();
}());
