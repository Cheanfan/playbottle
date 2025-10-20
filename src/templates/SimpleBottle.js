import {
  Mesh,
  MeshBasicMaterial,
  BufferGeometry,
  BufferAttribute,
  Vector3,
  MeshPhysicalMaterial,
  DoubleSide,
} from "three";
import { ArcLine, SimpleArcLineList } from "../engine3D/shapes";
import {
  createInnerThread,
  createThread,
  makeCurvePointsOffset,
  rotateColumnPoints,
} from "../engine3D/utils";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

const ROTATESEGMENTS = 30;

const simpleParams = {
  topRadius: 30,
  bottomRadius: 30,
  height: 120,
  neckRadius: 15,
  neckHeight: 18,
  bottomCorner: 5,
  topCorner: 5,
  thickness: 3,

  // thread
  threadRounds: 1.5,
  threadHeightRatio: 0.5,
  crestWidthRatio: 0.125,
  crestHeightRatio: 0.086,

  // cap
  capCorner: 2,
  capThickness: 3,
};

const simpleBottleState = {
  bodyShapeList: null,
  capShapeList: null,
};

const getBodySimpleShapeList = () => {
  const O = new Vector3();
  const A = new Vector3(simpleParams.bottomRadius, 0, 0);
  const B = new Vector3(simpleParams.topRadius, simpleParams.height, 0);
  const C = new Vector3(simpleParams.neckRadius, simpleParams.height, 0);
  const D = new Vector3(
    simpleParams.neckRadius,
    simpleParams.height + simpleParams.neckHeight,
    0
  );
  const arcLine1 = new ArcLine(O, A, B, simpleParams.bottomCorner);
  const arcLine2 = new ArcLine(arcLine1.oc, B, C, simpleParams.topCorner);
  const arcLine3 = new ArcLine(arcLine2.oc, C, D, simpleParams.thickness);
  const simpleArcLineList = new SimpleArcLineList([
    arcLine1,
    arcLine2,
    arcLine3,
    D,
  ]);
  simpleArcLineList.name = "body";
  simpleBottleState.bodyShapeList = simpleArcLineList;
};

const getCapSimpleShapeList = () => {
  const A = new Vector3(
    simpleParams.neckRadius +
      simpleParams.capThickness +
      simpleParams.crestHeightRatio * simpleParams.neckHeight,
    0,
    0
  );
  const B = new Vector3(
    simpleParams.neckRadius +
      simpleParams.capThickness +
      simpleParams.crestHeightRatio * simpleParams.neckHeight,
    simpleParams.neckHeight + simpleParams.capCorner,
    0
  );
  const C = new Vector3(0, simpleParams.neckHeight + simpleParams.capCorner, 0);
  const arcLine = new ArcLine(A, B, C, simpleParams.capCorner);
  const simpleArcLineList = new SimpleArcLineList([arcLine, C]);
  simpleArcLineList.name = "cap";
  simpleBottleState.capShapeList = simpleArcLineList;
};

const setupBottle = (engine2D, engine3D) => {
  getBodySimpleShapeList();
  const outerPoints = makeCurvePointsOffset(
    simpleBottleState.bodyShapeList.spacedPoints,
    0
  );
  const innerPoints = makeCurvePointsOffset(
    simpleBottleState.bodyShapeList.spacedPoints,
    simpleParams.thickness
  );
  const outer = rotateColumnPoints(outerPoints, Math.PI * 2, ROTATESEGMENTS);
  const inner = rotateColumnPoints(innerPoints, Math.PI * 2, ROTATESEGMENTS);
  let bodyGeometry = makeSolidGeometry(outer, inner);

  const bodyThread = createThread({
    crestWidth: simpleParams.crestWidthRatio * simpleParams.neckRadius,
    pitch:
      (simpleParams.neckHeight * simpleParams.threadHeightRatio) /
      simpleParams.threadRounds,
    rounds: simpleParams.threadRounds,
    radius: simpleParams.neckRadius,
    angle: 60,
    crestHeight: simpleParams.crestHeightRatio * simpleParams.neckHeight,
  });
  const bodyThreadGeo = new BufferGeometry().setFromPoints(bodyThread.points);
  bodyThreadGeo.setIndex(
    new BufferAttribute(new Uint16Array(bodyThread.indices), 1)
  );
  bodyThreadGeo.computeVertexNormals();
  bodyThreadGeo.translate(
    0,
    (1 - simpleParams.threadHeightRatio) * 0.5 * simpleParams.neckHeight +
      simpleParams.height,
    0
  );

  bodyGeometry = mergeGeometries([bodyGeometry, bodyThreadGeo]);

  const bodyMesh = new Mesh(
    bodyGeometry,
    new MeshPhysicalMaterial({
      envMap: engine3D.envMap,
      side: DoubleSide,
      color: 0x223399,
      roughness: 0,
      transmission: 1,
    })
  );
  engine3D.scene.add(bodyMesh);

  // cap
  const innerCapDepth =
    simpleParams.neckHeight +
    simpleParams.capCorner -
    simpleParams.capThickness;
  getCapSimpleShapeList();
  const outerCapPoints = makeCurvePointsOffset(
    simpleBottleState.capShapeList.spacedPoints,
    0
  );
  const innerCapPoints = makeCurvePointsOffset(
    simpleBottleState.capShapeList.spacedPoints,
    simpleParams.capThickness
  );
  const outerCap = rotateColumnPoints(
    outerCapPoints,
    Math.PI * 2,
    ROTATESEGMENTS
  );
  const innerCap = rotateColumnPoints(
    innerCapPoints,
    Math.PI * 2,
    ROTATESEGMENTS
  );
  let capGeometry = makeSolidGeometry(outerCap, innerCap, true);
  const capThread = createInnerThread({
    crestWidth: simpleParams.crestWidthRatio * simpleParams.neckRadius,
    pitch:
      (innerCapDepth * simpleParams.threadHeightRatio) /
      simpleParams.threadRounds,
    rounds: simpleParams.threadRounds,
    radius: simpleParams.neckRadius,
    angle: 60,
    crestHeight: simpleParams.crestHeightRatio * simpleParams.neckHeight,
  });
  const innerThreadGeo = new BufferGeometry().setFromPoints(capThread.points);
  innerThreadGeo.setIndex(
    new BufferAttribute(new Uint16Array(capThread.indices), 1)
  );
  innerThreadGeo.computeVertexNormals();
  innerThreadGeo.translate(
    0,
    (1 - simpleParams.threadHeightRatio) * 0.5 * innerCapDepth,
    0
  );

  capGeometry = mergeGeometries([capGeometry, innerThreadGeo]);

  const capMesh = new Mesh(
    capGeometry,
    new MeshPhysicalMaterial({
      envMap: engine3D.envMap,
      side: DoubleSide,
      color: 0xffffff,
      roughness: 0,
    })
  );
  capMesh.position.y = simpleParams.height + simpleParams.capCorner;
  engine3D.scene.add(capMesh);

  console.log(simpleBottleState, "simpleBottleState");

  // draw 2d
  outerPoints.reverse();
  innerPoints.reverse();
  const leftHalfBodyOuterPoints = outerPoints.map((p) => {
    const p1 = p.clone();
    p1.x = -p1.x;
    return p1;
  });
  leftHalfBodyOuterPoints.reverse();

  const leftHalfBodyInnertPoints = innerPoints.map((p) => {
    const p1 = p.clone();
    p1.x = -p1.x;
    return p1;
  });
  leftHalfBodyInnertPoints.reverse();

  const leftHalfCapOuterPoints = outerCapPoints.map((p) => {
    const p1 = p.clone();
    p1.x = -p1.x;
    return p1;
  });
  leftHalfCapOuterPoints.reverse();

  const leftHalfCapInnertPoints = innerCapPoints.map((p) => {
    const p1 = p.clone();
    p1.x = -p1.x;
    return p1;
  });
  leftHalfCapInnertPoints.reverse();
  outerPoints.push(...leftHalfBodyOuterPoints);
  innerPoints.push(...leftHalfBodyInnertPoints);
  outerCapPoints.push(...leftHalfCapOuterPoints);
  innerCapPoints.push(...leftHalfCapInnertPoints);

  engine2D.addShapeList({
    name: "body",
    points: [outerPoints, innerPoints],
  });
  engine2D.addShapeList({
    name: "cap",
    points: [outerCapPoints, innerCapPoints],
  });
  engine2D.updateDraw();
};

const draw2D = (engine2D) => {};

const makeSolidGeometry = (outer, inner, coverEnd = false) => {
  const points = [...inner.points, ...outer.points];
  let outerIndex = [...outer.indices];
  outerIndex.forEach((value, index) => {
    outerIndex[index] += inner.points.length;
  });
  let index = [...inner.indices, ...outerIndex];
  if (!coverEnd) {
    for (let i = 0; i < ROTATESEGMENTS - 1; i++) {
      let leftTop = i * inner.points2d.length + inner.points2d.length - 1;
      let leftBottom =
        i * outer.points2d.length +
        outer.points2d.length -
        1 +
        inner.points.length;
      let rightTop = leftTop + inner.points2d.length;
      let rightBottom = leftBottom + outer.points2d.length;
      if (i === ROTATESEGMENTS - 2) {
        rightTop = inner.points2d.length - 1;
        rightBottom = outer.points2d.length - 1 + inner.points.length;
      }
      index.push(
        leftTop,
        leftBottom,
        rightBottom,
        leftTop,
        rightBottom,
        rightTop
      );
    }
  } else {
    for (let i = 0; i < ROTATESEGMENTS - 1; i++) {
      let leftTop = i * inner.points2d.length;
      let leftBottom = i * outer.points2d.length + inner.points.length;
      let rightTop = leftTop + inner.points2d.length;
      let rightBottom = leftBottom + outer.points2d.length;
      if (i === ROTATESEGMENTS - 2) {
        rightTop = 0;
        rightBottom = inner.points.length;
      }
      index.push(
        leftTop,
        leftBottom,
        rightBottom,
        leftTop,
        rightBottom,
        rightTop
      );
    }
  }

  let geometry = new BufferGeometry().setFromPoints(points);

  geometry.setIndex(new BufferAttribute(new Uint16Array(index), 1));
  geometry.computeVertexNormals();

  return geometry;
};

export { getBodySimpleShapeList, simpleParams, simpleBottleState, setupBottle };
