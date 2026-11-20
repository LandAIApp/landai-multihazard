var apm = ee.Geometry.Polygon([[[-75.978789190000001,9.3715601399999997],[-76.020366150000001,9.3531703299999993],[-76.041954180000005,9.3099942500000008],[-76.033958609999999,9.2564239399999995],[-76.016368360000001,9.2404328000000007],[-75.975278450000005,9.2347006799999996],[-75.959599819999994,9.1876620399999993],[-75.890038369999999,9.1508824299999993],[-75.905229950000006,9.0565347099999993],[-75.907628619999997,8.9941692700000004],[-75.917223300000003,8.9086166799999997],[-75.983586529999997,8.8734361800000006],[-76.009971910000004,8.8022756100000006],[-76.070738230000003,8.6783442900000001],[-76.138277729999999,8.5951710899999991],[-76.133903230000001,8.5424196099999996],[-76.073271360000007,8.5167965300000006],[-76.057145759999997,8.4872501800000002],[-76.066740449999998,8.4168891800000001],[-76.142698350000003,8.3401317099999996],[-76.167884400000005,8.2609755800000002],[-76.175879969999997,8.2014085899999998],[-76.170283069999996,8.1582325099999995],[-76.154659039999999,8.1422339600000004],[-76.166685060000006,8.0902701700000001],[-76.184275310000004,8.0546898900000006],[-76.208461909999997,8.0271051799999995],[-76.187673430000004,8.0015193599999996],[-76.171282509999998,8.0127131499999997],[-76.135102560000007,8.0422967599999993],[-76.085530030000001,8.0862723899999995],[-76.043153520000004,8.1454395999999996],[-76.020233149999996,8.1985018099999998],[-76.012025480000005,8.1991173899999996],[-75.998218210000005,8.2030194499999993],[-75.984410929999996,8.2090226099999999],[-75.971203979999999,8.2210289299999992],[-75.960998610000004,8.2357366699999996],[-75.95289434,8.2501442600000008],[-75.951993869999995,8.2735565900000001],[-75.953494660000004,8.2885644900000006],[-75.95289434,8.3065739700000005],[-75.957096550000003,8.3413923099999998],[-75.953119459999996,8.3631537700000003],[-75.943739519999994,8.3814446500000006],[-75.941182190000006,8.3884195199999994],[-75.938306850000004,8.3878345400000001],[-75.933979559999997,8.3872903300000008],[-75.930467489999998,8.3873412799999993],[-75.928155709999999,8.3878159100000005],[-75.925929780000004,8.3883756300000005],[-75.923619799999997,8.3896179899999996],[-75.921481330000006,8.3909452400000006],[-75.919129889999994,8.3927848100000002],[-75.917000189999996,8.3978655],[-75.916020239999995,8.4000857399999997],[-75.91581008,8.40179236],[-75.915514950000002,8.4037977399999999],[-75.915519950000004,8.40593039],[-75.915352519999999,8.4075942500000007],[-75.913470529999998,8.4087502599999997],[-75.913262149999994,8.4112246299999995],[-75.912754430000007,8.4139129500000003],[-75.912073969999994,8.4160045399999994],[-75.911136589999998,8.4181393700000005],[-75.908661409999993,8.4221118500000003],[-75.907636740000001,8.4235644300000008],[-75.906869470000004,8.4251870199999992],[-75.906189459999993,8.4274918599999999],[-75.904824360000006,8.4299262499999994],[-75.904356230000005,8.4312495799999994],[-75.904531250000005,8.4328273399999993],[-75.905348720000006,8.4343609700000002],[-75.907022839999996,8.4358499699999996],[-75.913239599999997,8.4381388099999999],[-75.917355900000004,8.4397926699999992],[-75.919071099999996,8.4405137499999991],[-75.921935579999996,8.4416983499999994],[-75.908564749999996,8.4818099999999994],[-75.905496799999995,8.50854496],[-75.883242129999999,8.5556122999999999],[-75.839527599999997,8.5825263199999995],[-75.77351994,8.6019789099999997],[-75.742920359999999,8.6115959199999992],[-75.732429080000003,8.6249286000000005],[-75.727401999999998,8.6485339900000007],[-75.722372949999993,8.7112537299999993],[-75.714035229999993,8.7387682200000008],[-75.680684339999999,8.7721191100000002],[-75.650668530000004,8.8088051000000007],[-75.603977279999995,8.8479924000000008],[-75.584800509999994,8.9071902400000003],[-75.57396147,8.9605516699999992],[-75.577092989999997,8.9684936200000003],[-75.576274479999995,8.9697087799999995],[-75.575122759999999,8.9706387500000009],[-75.574684570000002,8.9713492099999996],[-75.574384100000003,8.9723324499999997],[-75.574495679999998,8.9734515500000001],[-75.574689340000006,8.97437942],[-75.575157529999998,8.9752795699999997],[-75.57578986,8.9757972699999993],[-75.576943999999997,8.97639605],[-75.578427250000004,8.9767486200000004],[-75.57930605,8.9768564400000006],[-75.580380939999998,8.9768318600000008],[-75.597307099999995,9.0197495100000005],[-75.649505210000001,9.0711911300000008],[-75.643774840000006,9.0805214200000002],[-75.640637769999998,9.0910201399999995],[-75.636537480000001,9.0912042799999995],[-75.633856710000003,9.0920087200000008],[-75.630505729999996,9.0930142299999996],[-75.628630279999996,9.0942171300000005],[-75.626553889999997,9.0955536499999994],[-75.624411350000003,9.0974234599999999],[-75.622470419999999,9.0995594999999998],[-75.621333340000007,9.1012276300000003],[-75.620062599999997,9.1031625700000003],[-75.618992899999995,9.1050305199999997],[-75.616583980000001,9.1080337500000006],[-75.614711139999997,9.1108361099999993],[-75.612837479999996,9.1131719400000009],[-75.611635070000005,9.1159065100000003],[-75.611236689999998,9.1182398500000001],[-75.610905470000006,9.1206397199999998],[-75.610374530000001,9.1239063399999996],[-75.610311670000002,9.1263724100000001],[-75.610853599999999,9.1295705799999993],[-75.611595480000005,9.1320353000000001],[-75.612741810000003,9.1356989800000008],[-75.613079859999999,9.1372979500000007],[-75.614359660000005,9.1405615099999995],[-75.615436000000003,9.1424924700000005],[-75.616309779999995,9.14362399],[-75.618323899999993,9.1448868599999997],[-75.619800819999995,9.1457507600000003],[-75.621144200000003,9.1469481100000003],[-75.621883310000001,9.1477466199999995],[-75.622986359999999,9.1500828700000003],[-75.648572180000002,9.2252412199999991],[-75.701342940000004,9.24922793],[-75.800487989999993,9.2484283699999992],[-75.827566820000001,9.2847284899999991],[-75.81567957,9.3443752],[-75.811063840000003,9.3881651099999992],[-75.842064949999994,9.4235313400000003],[-75.85850173,9.4251602800000001],[-75.861607050000003,9.4246611799999993],[-75.865603280000002,9.42423769],[-75.869475859999994,9.4239039099999999],[-75.872166399999998,9.4236736499999996],[-75.874485419999999,9.4234666499999999],[-75.876625070000003,9.4235731400000002],[-75.880048590000001,9.4237770399999992],[-75.882818779999994,9.4238819199999995],[-75.886344350000002,9.4243650199999998],[-75.887910070000004,9.42459588],[-75.889723979999999,9.4250161699999992],[-75.891753159999993,9.4259502200000007],[-75.893984450000005,9.4266601300000001],[-75.896531460000006,9.4275369399999995],[-75.89872905,9.4282692600000004],[-75.899266600000004,9.4285043399999999],[-75.902753329999996,9.4295418699999995],[-75.922820200000004,9.4315268999999997],[-75.953643700000001,9.4198827499999993],[-75.953627749999995,9.4147928499999995],[-75.953884130000006,9.4103938199999995],[-75.953741140000005,9.4071954299999998],[-75.955672120000003,9.4016589699999997],[-75.958004410000001,9.3956549299999992],[-75.959602680000003,9.3911856300000007],[-75.96308114,9.3871777000000005],[-75.967230389999997,9.3831012600000001],[-75.970710909999994,9.3798929500000003],[-75.973186119999994,9.3771538700000008],[-75.978789190000001,9.3715601399999997]]])
Map.addLayer(apm, '','AOI')
Map.centerObject(apm)

var MAX_CLOUD_PROBABILITY = 50
function maskS2clouds(image) {
  var qa = image.select('QA60');
  //var scl = image.select('SCL');

  // Bits 10 and 11 are clouds and cirrus, respectively.
  var cloudBitMask = 1 << 10;
  var cirrusBitMask = 1 << 11;

  // Both flags should be set to zero, indicating clear conditions.
  var mask = qa.bitwiseAnd(cloudBitMask).eq(0)
      .and(qa.bitwiseAnd(cirrusBitMask).eq(0))
      //.and(scl.eq(9));

  return image.updateMask(mask).divide(10000).copyProperties(image,['system:time_start']);
}

function maskClouds1(img) {var clouds = ee.Image(img.get('cloud_mask')).select('probability');
  var isNotCloud = clouds.lt(MAX_CLOUD_PROBABILITY);
  return img.updateMask(isNotCloud);
}

function maskEdges(s2_img) {
  return s2_img.updateMask(s2_img.select('B8A').mask().updateMask(s2_img.select('B9').mask()));
}

function gimagest(aoi, fecha1, fecha2){
  //Imagen
  var datasets2s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                    .filterDate(fecha1, fecha2)
                    // Pre-filter to get less cloudy granules.
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',50))
                    .filterBounds(aoi)
                    .map(maskS2clouds);
  var datasets2s2 = datasets2s2.map(function(img){
  return img.set('Date', ee.Date(img.get('system:time_start')).format('YYYY-MM-dd'));//FORMAT DATES
  })
  
  var s2Clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY');
  
  var criteria = ee.Filter.and(ee.Filter.bounds(aoi), ee.Filter.date(fecha1, fecha2));
  s2Clouds = s2Clouds.filter(criteria);
  
  var s2SrWithCloudMask = ee.Join.saveFirst('cloud_mask').apply({
    primary: datasets2s2,
    secondary: s2Clouds,
    condition: ee.Filter.equals({leftField: 'system:index', rightField: 'system:index'})
  });
  
  var s2CloudMasked = ee.ImageCollection(s2SrWithCloudMask).map(maskClouds1)//.median();
  print("Num images: ",s2CloudMasked.size().getInfo())
  var imagen_a1 = s2CloudMasked.median().clip(aoi)
  
  var imagenmc_a1 = imagen_a1.select('B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12')
  
  var imagen_zb = imagenmc_a1.clip(aoi);
  return imagen_zb;
}

var trueColorVis = {
  min: 0, max: 0.4, bands: ['B8', 'B11', 'B4']
};

var vis = {min: 0, max: 1, palette: [
    'FFFFFF', 'CE7E45', 'DF923D', '74A901',
    '66A000', '529400', '3E8601', '207401',
    '012E01', '011D01'
  ]};

var fecha1 = '2026-01-01'
var fecha2 = '2026-01-26'
var imagen_zb = gimagest(apm, fecha1, fecha2)
Map.addLayer(imagen_zb,trueColorVis, 'Imagen-Pre');
var fecha3 = '2026-02-02'
var fecha4 = '2026-02-15'
var imagen_zb2 = gimagest(apm, fecha3, fecha4)
Map.addLayer(imagen_zb2,trueColorVis, 'Imagen-Post');

//RADAR

function speckleFilterDb(imgDb) {
  // Simple, reproducible speckle reduction: focal median
  return imgDb.focal_median({radius: 30, units: 'meters'});
}

function toLinear(img) {
  return ee.Image(10).pow(img.divide(10));
}
// -------------------- Build pre/post composites --------------------
function getS1Composite(aoi, startDate, endDate) {
  var col = ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(aoi)
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
    .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
    .filterDate(startDate, endDate)

  print("Num images Radar: ",col.size().getInfo())
  
  var colmed = ee.Image(col.median()).clip(aoi);
  var vv = colmed.select('VV').focal_median({radius: 30, units: 'meters'}).rename('VV');
  var vh = colmed.select('VH').focal_median({radius: 30, units: 'meters'}).rename('VH');  
  // median composites in linear, then convert to dB and filter
  // var vvDb = speckleFilterDb(toDb(col.select('VV').median().clip(aoi))).rename('VV_db');
  // var vhDb = speckleFilterDb(toDb(col.select('VH').median().clip(aoi))).rename('VH_db');

  return vv.addBands(vh);
}

var preImg  = getS1Composite(apm, fecha1, fecha2);
var postImg = getS1Composite(apm, fecha3, fecha4);
var visRadar = {min:-25, max:0, bands: ['VH', 'VV', 'VH']}
Map.addLayer(preImg, visRadar, 'S1-Pre', false);
Map.addLayer(postImg, visRadar, 'S1-Post', false);


// -------------------- Temporal change: log-ratio VV + VH --------------------

var lrVV = postImg.select('VV').divide(preImg.select('VV')).log10().rename('lrVV'); 
var lrVH = postImg.select('VH').divide(preImg.select('VH')).log10().rename('lrVH')

// var preVV_lin  = toLinear(preImg.select('VV'));
// var postVV_lin = toLinear(postImg.select('VV'));
// var lrVV = postVV_lin.divide(preVV_lin).log10().rename('lrVV');

// var preVH_lin  = toLinear(preImg.select('VH'));
// var postVH_lin = toLinear(postImg.select('VH'));
// var lrVH = postVH_lin.divide(preVH_lin).log10().rename('lrVH');

// Combined index: robust & simple
var lrCombined = lrVV.min(lrVH).rename('lrCombined');

Map.addLayer(lrVV, {min:-0.5, max:0.5}, 'logRatio VV', false);
Map.addLayer(lrVH, {min:-0.5, max:0.5}, 'logRatio VH', false);
Map.addLayer(lrCombined, {min:-0.5, max:0.5}, 'logRatio combined (min)', false);

// --------------------Otsu threshold --------------------
function otsuThreshold(image, region, scale) {
  var band = ee.String(image.bandNames().get(0));

  var hist = image.reduceRegion({
    reducer: ee.Reducer.histogram({maxBuckets: 256}),
    geometry: region,
    scale: scale,
    bestEffort: true,
    maxPixels: 1e13
  });

  var h = ee.Dictionary(hist.get(band));
  // Fallback por si el histograma viene nulo
  var fallback = ee.Number(-0.3);

  return ee.Algorithms.If(h, _otsuFromHist(h), fallback);
}

function _otsuFromHist(h) {
  var counts = ee.Array(h.get('histogram'));
  var means  = ee.Array(h.get('bucketMeans'));

  var size  = means.length().get([0]);
  var total = counts.reduce(ee.Reducer.sum(), [0]).get([0]);

  var sum  = means.multiply(counts).reduce(ee.Reducer.sum(), [0]).get([0]);
  var mean = sum.divide(total);

  // Umbrales posibles: 1..size-1
  var bcvList = ee.List.sequence(1, ee.Number(size).subtract(1)).map(function(i) {
    i = ee.Number(i);

    var c1 = counts.slice(0, 0, i);
    var c2 = counts.slice(0, i, size);

    var s1 = c1.reduce(ee.Reducer.sum(), [0]).get([0]);
    var s2 = c2.reduce(ee.Reducer.sum(), [0]).get([0]);

    var w1 = s1.divide(total);
    var w2 = s2.divide(total);

    // Evitar divide-by-zero en medias
    var m1 = means.slice(0, 0, i).multiply(c1).reduce(ee.Reducer.sum(), [0]).get([0])
      .divide(ee.Number(s1).max(1));
    var m2 = means.slice(0, i, size).multiply(c2).reduce(ee.Reducer.sum(), [0]).get([0])
      .divide(ee.Number(s2).max(1));

    return w1.multiply(m1.subtract(mean).pow(2)).add(w2.multiply(m2.subtract(mean).pow(2)));
  });
  var x = means.slice(0, 1, size);
  print(ui.Chart.array.values(ee.Array(bcvList), 0, x));
  var bcv = ee.Array(bcvList); 
  print(bcv)// length = size-1
  var idx0 = bcv.argmax().get(0);   // <- importante: [0,0] para escalar real
  var idx = ee.Number(idx0).add(1);      // shift porque empezamos en 1

  return means.get([idx]);
}

var scale = 10;
var thr = ee.Number(otsuThreshold(lrCombined, apm, scale));
print('Otsu threshold:', thr);
Map.addLayer(lrCombined, {min:0, max:1}, 'Flood mask (VV+VH)In', true);
// Flood = strong negative change 
var floodMask = lrCombined.lte(ee.Number(thr)).selfMask();
Map.addLayer(floodMask, {min:0, max:1}, 'Flood mask (VV+VH)', true);

// Optional slope mask to reduce false positives in steep terrain
var maxSlopeDeg = 5;
var dem = ee.Image('USGS/SRTMGL1_003'); // global DEM (SRTM)
var slope = ee.Terrain.slope(dem);
var slopeMask = slope.lte(maxSlopeDeg);
// Mask slope <5
floodMask = floodMask//.updateMask(slopeMask);
// Simple cleaning: remove very small patches (connected pixel count)
var minConnPixels = 20; 
var conn = floodMask.connectedPixelCount(100, true);
floodMask = floodMask.updateMask(conn.gte(minConnPixels));

Map.addLayer(floodMask, {min:0, max:1}, 'Flood mask (VV+VH) Filter', true);

// --------------------Export raster mask --------------------
Export.image.toDrive({
  image: floodMask.rename('FloodMask'),
  description: 'FloodMask_S1_VV_VH_DESC',
  region: apm,
  scale: scale,
  maxPixels: 1e13
});

