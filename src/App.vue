<script setup>
import { ArcCurve, BoxGeometry, BufferAttribute, BufferGeometry, CatmullRomCurve3, DoubleSide, EquirectangularReflectionMapping, GridHelper, Group, Line, Line3, LineBasicMaterial, LineCurve3, Mesh, MeshPhysicalMaterial, PerspectiveCamera, Points,Color, PointsMaterial, Quaternion, Scene, Vector3, WebGLRenderer } from 'three';
import { LineMaterial, OrbitControls, RGBELoader } from 'three/examples/jsm/Addons.js';
import Two from 'two.js';
import { Anchor } from 'two.js/src/anchor';
import { Vector } from 'two.js/src/vector';
import { nextTick, onMounted, ref } from 'vue';
import { ArcLine, SimpleArcLineList } from './engine3D/shapes';
import { makeCurvePointsOffset, rotateColumnPoints } from './engine3D/utils';
import { Engine2D } from './engine2D/Engine2D';
import { getBodySimpleShapeList, setupBottle, simpleBottleState, simpleParams } from './templates/SimpleBottle';


function removeSelfIntersections(points) {
  const EPS = 1e-9;
  // 复制一份，避免改动原数组
  const pts = points.map(p => p.clone());

  if (pts.length < 4) return pts; // 少于两段不可能自交

  // 线段严格内点相交（排除端点相交），返回交点与参数 t,u
  function intersect2D(A, B, C, D) {
    const ax = A.x, ay = A.y, bx = B.x, by = B.y;
    const cx = C.x, cy = C.y, dx = D.x, dy = D.y;

    const r_x = bx - ax, r_y = by - ay;
    const s_x = dx - cx, s_y = dy - cy;

    const denom = r_x * s_y - r_y * s_x;
    if (Math.abs(denom) < EPS) return null; // 平行或共线，忽略

    const t = ((cx - ax) * s_y - (cy - ay) * s_x) / denom;
    const u = ((cx - ax) * r_y - (cy - ay) * r_x) / denom;

    // 严格在两条线段内部（避免端点/相邻段误判）
    if (t > EPS && t < 1 - EPS && u > EPS && u < 1 - EPS) {
      return { 
        x: ax + t * r_x,
        y: ay + t * r_y,
        t, u
      };
    }
    return null;
  }

  // 去重相邻重复点（可能因数值误差产生）
  function squashConsecutiveDuplicates(arr) {
    const out = [];
    for (let k = 0; k < arr.length; k++) {
      if (k === 0) { out.push(arr[k]); continue; }
      const prev = out[out.length - 1];
      if (Math.hypot(arr[k].x - prev.x, arr[k].y - prev.y) > EPS) {
        out.push(arr[k]);
      }
    }
    return out;
  }

  let changed = true;
  while (changed) {
    changed = false;
    outer:
    for (let i = 0; i < pts.length - 1; i++) {
      for (let j = i + 2; j < pts.length - 1; j++) {
        // 对开放折线而言，(i,i+1) 与 (i+1,i+2) 相邻，已由 j = i+2 起跳过
        const inter = intersect2D(pts[i], pts[i + 1], pts[j], pts[j + 1]);
        if (inter) {
          // 构造交点（z 取 i 点的 z，通常为 0）
          const interV = new Vector3(inter.x, inter.y, pts[i].z);

          // 在 i 后插入交点，并删除 (i, j) 区间的点：即删掉 i+1..j
          // splice 的第二个参数为删除个数：j - i
          pts.splice(i + 1, j - i, interV);

          // 清理可能出现的相邻重复点
          const cleaned = squashConsecutiveDuplicates(pts);
          pts.length = 0; pts.push(...cleaned);

          changed = true;
          break outer; // 结构改变后从头重新搜索
        }
      }
    }
  }

  return pts;
}

const container = ref(null);
const two = ref(null);

const engine = {
  renderer: null,
  scene: null,
  camera: null,
  orbit: null,
  envMap: null,
  object: null,
}

const engineTwo = {
  two: null,
  value: null
}



const init = () => {
  nextTick(setupEnv);
}

onMounted(init);

const CORNERSEGMENTS = 20;
const LINESEGMENTS = 20;
const ROTATESEGMENTS = 40;

const CURVEONLY = false;

const generateBottleBody = (offset=0) => {
  let points = simpleBottleState.bodyShapeList.spacedPoints;
  points = makeCurvePointsOffset(points, offset);
  return rotateColumnPoints(points, Math.PI * 2, ROTATESEGMENTS);
}

const generateBottleBody2 = (params, offset=0) => {
  console.log(params);
  const {
    neckRadius,
    topRadius,
    bottomRadius,
    height,
    neckHeight,
    bottomCorner,
    topCorner,
    thickness
  } = params;

  // const O = new Vector3();
  // const A = new Vector3(bottomRadius, 0, 0);
  // const B = new Vector3(topRadius, height, 0);
  // const C = new Vector3(neckRadius, height, 0);
  // const D = new Vector3(neckRadius, height + neckHeight, 0);
  // const arcOAB = new ArcLine(O, A, B, bottomCorner);
  // const arcABC = new ArcLine(A, B, C, topCorner);
  // const simpleArcLine = new SimpleArcLineList([arcOAB, arcABC, D]);

  const O = new Vector3();
  const A = new Vector3(bottomRadius, 0, 0);
  const B = new Vector3(topRadius, height, 0);
  const C = new Vector3(neckRadius, height, 0);
  const roundResA = roundCorner(O, A, B, bottomCorner);
  const OB = roundResA.oc;
  const roundResB = roundCorner(OB, B, C, topCorner);

  console.log('roundResB', roundResB)

  const points = [];

  const O_O1_A = new LineCurve3(O, roundResA.oa);

  points.push(...O_O1_A.getPoints(LINESEGMENTS));

  let axis_0 = roundResA.oa.clone().sub(roundResA.round.o).normalize();
  let axis_1 = roundResA.oc.clone().sub(roundResA.round.o).normalize();
  let axis = axis_0.clone().cross(axis_1).normalize();
  

  let rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResA.round.angle/(CORNERSEGMENTS-1));
  let dir = axis_0.clone();
  points.pop();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResA.round.o.clone().add(dir.clone().multiplyScalar(bottomCorner));
    points.push(target);
  }

  const O1_B_B = new LineCurve3(roundResA.oc, roundResB.oa);
  points.pop();
  points.push(...O1_B_B.getPoints(LINESEGMENTS));

  axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  axis = axis_0.clone().cross(axis_1);
  

  rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResB.round.angle/(CORNERSEGMENTS-1));
  dir = axis_0.clone();
  points.pop();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o.clone().add(dir.clone().multiplyScalar(topCorner));
    points.push(target);
  }

  const O2_C = new LineCurve3(roundResB.oc, C);
  points.pop();
  points.push(...O2_C.getPoints(LINESEGMENTS));

  const D = new Vector3(neckRadius, height + neckHeight, 0)
  const CD = new LineCurve3(C, D);
  points.pop();
  points.push(...CD.getPoints(LINESEGMENTS));
  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach(point => {
    if(prev) {
      const dist = point.distanceTo(prev);
      if(dist > 1e-5) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });
  const z = new Vector3(0, 0, -1);
  let f_points_temp = []
  for(let i=0; i<f_points.length; i++) {
    let prev = f_points[i-1];
    const current = f_points[i];
    let next = f_points[i+1];
    if(!prev) {
      prev = current.clone().add(current.clone().sub(next))
    }
    if(!next) {
      next = current.clone().add(current.clone().sub(prev))
    }
    const prev_current = current.clone().sub(prev).normalize();
    prev_current.cross(z);
    const current_next = next.clone().sub(current).normalize();
    current_next.cross(z);
    const normal = current_next;
    // prev_current.add(current_next).normalize();
    f_points_temp.push(current.clone().add(normal.multiplyScalar(offset)))
  }

  if(Math.abs(offset) > 0.01) {
    f_points = removeSelfIntersections(f_points_temp);
    // f_points = f_points_temp;
  }


  const totalPoints = [];
  const rotate_step = Math.PI * 2 / (ROTATESEGMENTS - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), rotate_step);
  let rotated_points = null;
  const indices = [];
  if(!CURVEONLY) {
    for(let i=0; i<ROTATESEGMENTS-1; i++) {
      if(rotated_points) {
        let origin_points = rotated_points;
        rotated_points = rotated_points.map(point => {
          return point.clone().applyQuaternion(rotateQuat);
        });
        // indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        for(let j=1; j<origin_points.length; j++) {
          const leftTop = (i-1) * origin_points.length + j-1;
          const leftBottom = (i-1) * origin_points.length + j;
          const rightTop = i * origin_points.length + j-1;
          const rightBottom = i * origin_points.length + j;
          indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        }
        if(i==ROTATESEGMENTS-2) {
          for(let j=1; j<origin_points.length; j++) {
            const leftTop = i * origin_points.length + j-1;
            const leftBottom = i * origin_points.length + j;
            const rightTop = j-1;
            const rightBottom = j;
            indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
          }
        }
      } else {
        rotated_points = f_points;
      }
      totalPoints.push(rotated_points)
    }
  } else {
    totalPoints.push(f_points)
  }




  const fin_points = totalPoints.flatMap(points => [...points]);
  const data = {
    indices,
    points: fin_points,
    row: f_points.length,
    points2d: f_points
  }

  return data;
}

const generateTag = (params, offset=0.1) => {
  const {
    gap,
    topRadius,
    bottomRadius,
    height,
    angle
  } = params;
  const A = new Vector3(bottomRadius + gap, -height/2, 0);
  const B = new Vector3(topRadius + gap, height/2, 0);

  const AB = new LineCurve3(A, B);
  const points = [];
  points.push(...AB.getPoints(LINESEGMENTS));

  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach(point => {
    if(prev) {
      const dist = point.distanceTo(prev);
      if(dist > 1e-5) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });
  const z = new Vector3(0, 0, -1);
  let f_points_temp = []
  for(let i=0; i<f_points.length; i++) {
    let prev = f_points[i-1];
    const current = f_points[i];
    let next = f_points[i+1];
    if(!prev) {
      prev = current.clone().add(current.clone().sub(next))
    }
    if(!next) {
      next = current.clone().add(current.clone().sub(prev))
    }
    const prev_current = current.clone().sub(prev).normalize();
    prev_current.cross(z);
    const current_next = next.clone().sub(current).normalize();
    current_next.cross(z);
    const normal = current_next;
    // prev_current.add(current_next).normalize();
    f_points_temp.push(current.clone().add(normal.multiplyScalar(offset)))
  }

  if(Math.abs(offset) > 0.01) {
    f_points = removeSelfIntersections(f_points_temp);
    // f_points = f_points_temp;
  }

  const totalPoints = [];
  const rotate_step = angle / (ROTATESEGMENTS - 1);
  let rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), rotate_step);
  let rotated_points = null;
  const indices = [];
  if(!CURVEONLY) {
    for(let i=0; i<ROTATESEGMENTS-1; i++) {
      if(rotated_points) {
        let origin_points = rotated_points;
        rotated_points = rotated_points.map(point => {
          return point.clone().applyQuaternion(rotateQuat);
        });
        // indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        for(let j=1; j<origin_points.length; j++) {
          const leftTop = (i-1) * origin_points.length + j-1;
          const leftBottom = (i-1) * origin_points.length + j;
          const rightTop = i * origin_points.length + j-1;
          const rightBottom = i * origin_points.length + j;
          indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        }
        // if(i==ROTATESEGMENTS-2) {
        //   for(let j=1; j<origin_points.length; j++) {
        //     const leftTop = i * origin_points.length + j-1;
        //     const leftBottom = i * origin_points.length + j;
        //     const rightTop = j-1;
        //     const rightBottom = j;
        //     indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        //   }
        // }
      } else {
        rotated_points = f_points;
      }
      totalPoints.push(rotated_points)
    }
  } else {
    totalPoints.push(f_points)
  }

  const fin_points = totalPoints.flatMap(points => [...points]);
  const data = {
    indices,
    points: fin_points,
    row: points.length
  }

  return data;

}

const generateBottleCapBody = (params, offset=0) => {
  const {
    neckCorner,
    radius,
    height
  } = params;
  const A = new Vector3(radius, 0, 0);
  const B = new Vector3(radius, height, 0);
  const C = new Vector3(0, height, 0);

  const points = [];

  const roundResB = roundCorner(A, B,C, neckCorner);
  const A_O1_A = new LineCurve3(A, roundResB.oa);

  points.push(...A_O1_A.getPoints(LINESEGMENTS));

  let axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  let axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  let axis = axis_0.clone().cross(axis_1).normalize();
  

  let rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResB.round.angle/(CORNERSEGMENTS-1));
  let dir = axis_0.clone();
  points.pop();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o.clone().add(dir.clone().multiplyScalar(neckCorner));
    points.push(target);
  }

  const O1_B_C = new LineCurve3(roundResB.oc, C);
  points.pop();
  points.push(...O1_B_C.getPoints(LINESEGMENTS));

  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach(point => {
    if(prev) {
      const dist = point.distanceTo(prev);
      if(dist > 1e-5) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });

  const z = new Vector3(0, 0, -1);
  let f_points_temp = []
  for(let i=0; i<f_points.length; i++) {
    let prev = f_points[i-1];
    const current = f_points[i];
    let next = f_points[i+1];
    if(!prev) {
      prev = current.clone().add(current.clone().sub(next))
    }
    if(!next) {
      next = current.clone().add(current.clone().sub(prev))
    }
    const prev_current = current.clone().sub(prev).normalize();
    prev_current.cross(z);
    const current_next = next.clone().sub(current).normalize();
    current_next.cross(z);
    const normal = current_next;
    // prev_current.add(current_next).normalize();
    f_points_temp.push(current.clone().add(normal.multiplyScalar(offset)))
  }

  if(Math.abs(offset) > 0.01) {
    f_points = removeSelfIntersections(f_points_temp);
    // f_points = f_points_temp;
  }


  const totalPoints = [];
  const rotate_step = Math.PI * 2 / (ROTATESEGMENTS - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), rotate_step);
  let rotated_points = null;
  const indices = [];
  for(let i=0; i<ROTATESEGMENTS-1; i++) {
    if(rotated_points) {
      let origin_points = rotated_points;
      rotated_points = rotated_points.map(point => {
        return point.clone().applyQuaternion(rotateQuat);
      });
      // indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
      for(let j=1; j<origin_points.length; j++) {
        const leftTop = (i-1) * origin_points.length + j-1;
        const leftBottom = (i-1) * origin_points.length + j;
        const rightTop = i * origin_points.length + j-1;
        const rightBottom = i * origin_points.length + j;
        indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
      }
      if(i==ROTATESEGMENTS-2) {
        for(let j=1; j<origin_points.length; j++) {
          const leftTop = i * origin_points.length + j-1;
          const leftBottom = i * origin_points.length + j;
          const rightTop = j-1;
          const rightBottom = j;
          indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        }
      }
    } else {
      rotated_points = f_points;
    }
    totalPoints.push(rotated_points)
  }

  console.log(indices)

  const fin_points = totalPoints.flatMap(points => [...points]);
  const data = {
    indices,
    points: fin_points,
    row: f_points.length
  }

  return data;
}

const roundCorner = (a, b, c, radius) => {
  const ab = b.clone().sub(a);
  const bc = c.clone().sub(b);
  const cosAlpha = ab.clone().normalize().dot(bc.clone().normalize().multiplyScalar(-1));
  let alpha = Math.acos(cosAlpha);
  const halfAlpha = alpha * 0.5;
  const oa  = b.clone().sub(
    ab.clone().normalize().multiplyScalar(radius/Math.tan(halfAlpha))
  );
  const oc = b.clone().add(
    bc.clone().normalize().multiplyScalar(radius/Math.tan(halfAlpha))
  );
  const rotateAxis = ab.clone().normalize().cross(bc.clone().normalize());
  const oa_o = rotateAxis.cross(ab.clone().normalize()).normalize().multiplyScalar(radius);
  const o = oa_o.add(oa);
  const round = {
    o,
    angle: Math.PI - alpha,
  }
  return {
    oa,
    oc,
    round
  }
}

const generateBottle = (params) => {
  console.log(params);
  const {
    neckRadius,
    topRadius,
    bottomRadius,
    height,
    neckHeight,
    bottomCorner,
    topCorner
  } = params;

  // bottom center to corner
  const tanTheta = (bottomRadius - topRadius) / height;
  const sinTheta = tanTheta / Math.sqrt(1+tanTheta*tanTheta);
  const a = bottomCorner / tanTheta;
  const b = bottomCorner + bottomCorner / sinTheta;
  const c = b * tanTheta;

  const C = new Vector3(bottomRadius - c, 0, 0);
  const O_C = new Vector3(bottomRadius, 0, 0);
  const oc_d = Math.sqrt(b*b + c*c);
  const oc_a = oc_d - a;
  const T = new Vector3(topRadius, height, 0);
  const OC_T = T.clone().sub(O_C).normalize();
  const A = O_C.clone().add(OC_T.clone().multiplyScalar(oc_a));

  const tanBeta = 1 / tanTheta;
  const Beta = Math.atan(tanBeta);
  const halfBeta = Beta / 2;
  const t_t0 = topCorner * Math.tan(halfBeta);
  const T0 = T.clone().sub(OC_T.clone().multiplyScalar(t_t0));
  const T1 = T.clone().add(new Vector3(-1, 0, 0).multiplyScalar(t_t0));

  const ocCurve = new CatmullRomCurve3([new Vector3(), C]);
  const ocPoints = ocCurve.getPoints(LINESEGMENTS);
  const bCornerPoints = [];
  const tCornerPoints = [];
  const beta_left = Math.PI - Beta;
  let axis = new Vector3(0, -1, 0);

  let rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), beta_left/(CORNERSEGMENTS-1));
  const bCornerCenter = new Vector3(C.x, bottomCorner, 0)
  for(let i=0; i< CORNERSEGMENTS; i++) {
    axis.applyQuaternion(rotateQuat).normalize();
    const target = bCornerCenter.clone().add(axis.clone().multiplyScalar(bottomCorner));
    bCornerPoints.push(target);
  }
  bCornerPoints.pop();
  bCornerPoints.push(A);

  const a_t0 = new CatmullRomCurve3([A, T0]).getPoints(LINESEGMENTS);

  rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), Beta/(CORNERSEGMENTS-1));
  const tCornerCenter = new Vector3(T1.x, T1.y - topCorner, 0);
  axis = T0.clone().sub(tCornerCenter).normalize();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    axis.applyQuaternion(rotateQuat).normalize();
    const target = tCornerCenter.clone().add(axis.clone().multiplyScalar(topCorner));
    tCornerPoints.push(target);
  }
  tCornerPoints.pop();
  tCornerPoints.push(T1);

  const t1_neck_bottom = new CatmullRomCurve3([T1, new Vector3(neckRadius, height, 0)]).getPoints(LINESEGMENTS);

  const neck_bottom_top = new CatmullRomCurve3([new Vector3(neckRadius, height + neckHeight, 0), new Vector3(neckRadius, height, 0)]).getPoints(LINESEGMENTS);
  

  const pointsArray = [...ocPoints, ...bCornerPoints, ...a_t0, ...tCornerPoints, ...t1_neck_bottom, ...neck_bottom_top];
  const f_points = [];
  let prev = null;
  pointsArray.forEach(point => {
    if(prev) {
      const dist = point.distanceTo(prev);
      if(dist > 1e-5) {
        f_points.push(point);
      }
    }
    prev = point;
  });

  const totalPoints = [];
  const rotate_step = Math.PI * 2 / (ROTATESEGMENTS - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), rotate_step);
  let rotated_points = null;
  const indices = [];
  for(let i=0; i<ROTATESEGMENTS-1; i++) {
    if(rotated_points) {
      let origin_points = rotated_points;
      rotated_points = rotated_points.map(point => {
        return point.clone().applyQuaternion(rotateQuat);
      });
      for(let j=1; j<origin_points.length; j++) {
        const leftTop = (i-1) * origin_points.length + j-1;
        const leftBottom = (i-1) * origin_points.length + j;
        const rightTop = i * origin_points.length + j-1;
        const rightBottom = i * origin_points.length + j;
        indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
      }
      if(i==ROTATESEGMENTS-2) {
        for(let j=1; j<origin_points.length; j++) {
          const leftTop = i * origin_points.length + j-1;
          const leftBottom = i * origin_points.length + j;
          const rightTop = j-1;
          const rightBottom = j;
          indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        }
      }
    } else {
      rotated_points = f_points;
    }
    totalPoints.push(rotated_points)
  }

  console.log(indices)

  const fin_points = totalPoints.flatMap(points => [...points]);
  const geometry = new BufferGeometry().setFromPoints(fin_points);
  geometry.setIndex(new BufferAttribute(new Uint16Array(indices), 1))
  geometry.computeVertexNormals();
  const mesh = new Mesh(
    geometry,
    new MeshPhysicalMaterial(
      {
        envMap: engine.envMap,
        side: DoubleSide,
        wireframe: false
      }
    )
  );

  return mesh;

}

const changeBottle = (engine2D, engine3D) => {
  setupBottle(engine2D, engine3D);
  return;
  const bottleOuter = generateBottleBody();
  const bottleInner = generateBottleBody(simpleParams.thickness);
  
  let points = [...bottleInner.points, ...bottleOuter.points];

  const bodyShapeList = getBodySimpleShapeList();
  engineTwo.value.addShapeList(bodyShapeList)

  engineTwo.two.scene.children.slice().forEach(child => engineTwo.two.remove(child));

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  bottleOuter.points2d.forEach(item => {
    if(item.x > maxX) {
      maxX = item.x;
    }
    if(item.x < minX) {
      minX = item.x;
    }
    if(item.y > maxY) {
      maxY = item.y;
    }
    if(item.y < minY) {
      minY = item.y;
    }
  });

  const outerCenterX = maxX * 0.5 + minX * 0.5;
  const outerCenterY = maxY * 0.5 + minY * 0.5;

  const width2D = engineTwo.two.width;
  const height2D = engineTwo.two.height;
  
  const min2DSize = Math.min(width2D, height2D);
  const pointSizeX = maxX - minX;
  const pointSizeY = maxY - minY;
  const max3DSize = Math.max(pointSizeX, pointSizeY);
  const sizeRate = min2DSize / max3DSize * 0.5;

  const transformCoord = (p) => {
    const newP = p.clone();
    newP.multiplyScalar(sizeRate);
    newP.y = maxY - newP.y;
    newP.add(new Vector3(width2D * 0.5 - outerCenterX, height2D * 0.5 - outerCenterY + 20, 0));
    return newP
  }

  const outerPoints2D = bottleOuter.points2d.map(item => {
    const newP = transformCoord(item);
    return new Anchor(newP.x, newP.y);
  });

  const bottomPoint = transformCoord(new Vector3(0, -10, 0));

  const topPoint = transformCoord( new Vector3(0, maxY + 10, 0));

  const centerDash = engineTwo.two.makeLine(bottomPoint.x, bottomPoint.y, topPoint.x, topPoint.y);
  centerDash.stroke = 'black';

  centerDash.dashes = [10, 5];


  const curve2DOuter = engineTwo.two.makeCurve(outerPoints2D, true);

  const innerPoints2D = bottleInner.points2d.map(item => {
    const newP = transformCoord(item);
    return new Anchor(newP.x, newP.y);
  });

  const curve2DInner = engineTwo.two.makeCurve(innerPoints2D, true);

  
  let p0 = transformCoord(new Vector3());
  let p00 = transformCoord(new Vector3(bottomRadius, 0, 0))
  drawDimensionLine(engineTwo.two, p0, p00, thickness + 20, bottomRadius);

  let p1 = transformCoord(new Vector3(0, height, 0))
  let p2 = transformCoord(new Vector3(topRadius, height, 0))

  let actualTopRadius = p2.x - p1.x;
  let actualBottomRadius = p00.x - p1.x;

  drawDimensionLine(engineTwo.two, p1, p2, -90, topRadius);

  p1 = transformCoord(new Vector3(0, height + neckHeight, 0))
  p2 = transformCoord(new Vector3(neckRadius, height + neckHeight, 0))
  drawDimensionLine(engineTwo.two, p1, p2, -25, neckRadius);

  p1 = transformCoord(new Vector3(neckRadius - thickness, height + neckHeight, 0))
  p2 = transformCoord(new Vector3(neckRadius, height + neckHeight, 0))
  drawDimensionLine(engineTwo.two, p1, p2, -5, thickness);

  p1 = transformCoord(new Vector3())
  p2 = transformCoord(new Vector3(0, height, 0))
  drawDimensionLine(engineTwo.two, p1, p2, Math.max(actualTopRadius, actualBottomRadius) + 20, height);

  const r1 = roundCorner(new Vector3(), new Vector3(bottomRadius, 0, 0), new Vector3(topRadius, height, 0), bottomCorner);
  let half = r1.oa.clone().sub(r1.round.o).normalize().add(
    r1.oc.clone().sub(r1.round.o).normalize()
  ).normalize();
  half = r1.round.o.clone().add(half.multiplyScalar(bottomCorner));
  console.log(r1, 'round')
  drawRadiusAnnotation(engineTwo.two, transformCoord(r1.round.o), transformCoord(half), bottomCorner)

  const r2 = roundCorner(new Vector3(bottomRadius, 0, 0), new Vector3(topRadius, height, 0), new Vector3(0, height, 0), bottomCorner);
  let half2 = r2.oa.clone().sub(r2.round.o).normalize().add(
    r2.oc.clone().sub(r2.round.o).normalize()
  ).normalize();
  half2 = r2.round.o.clone().add(half2.multiplyScalar(bottomCorner));
  drawRadiusAnnotation(engineTwo.two, transformCoord(r2.round.o), transformCoord(half2), topCorner)


  console.log(bottleOuter)
  
  let outerIndex = [...bottleOuter.indices]
  outerIndex.forEach((value, index) => {
    outerIndex[index] += bottleInner.points.length;
  });
  let index = [...bottleInner.indices, ...outerIndex];

  for(let i=0; i<ROTATESEGMENTS-1; i++) {
    let leftTop = i * bottleInner.points2d.length + bottleInner.points2d.length-1;
    let leftBottom = i * bottleOuter.points2d.length + bottleOuter.points2d.length-1 + bottleInner.points.length;
    let rightTop = leftTop + bottleInner.points2d.length;
    let rightBottom = leftBottom + bottleOuter.points2d.length;
    if(i===ROTATESEGMENTS-2) {
      rightTop = bottleInner.points2d.length-1;
      rightBottom = bottleOuter.points2d.length-1 + bottleInner.points.length
    }

    // let leftBottom = i * eachColumn + eachColumn-1;
    // let leftTop = leftBottom + fin_points.length;
    // let rightBottom = leftBottom + eachColumn;
    // if(i===ROTATESEGMENTS-2) {
    //   rightBottom = eachColumn-1;
    // }
    // let rightTop = rightBottom + fin_points.length;
    index.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
  }

  let geometry = new BufferGeometry().setFromPoints(points);

  if(!CURVEONLY) {
    geometry.setIndex(new BufferAttribute(new Uint16Array(index), 1))
    geometry.computeVertexNormals();
  }

  let bottleMesh;
  if(!CURVEONLY) {
    bottleMesh = new Mesh(
      geometry,
      new MeshPhysicalMaterial(
        {
          envMap: engine.envMap,
          side: DoubleSide,
          wireframe: false,
          color:223399,
          roughness: 0,
          transmission: 1
        }
      )
    );
  } else {
    bottleMesh = new Line(
      geometry,
      new LineBasicMaterial()
    );
  }

  const tagOuter = generateTag({
    gap: 1,
    topRadius: topRadius * 0.75 + bottomRadius * 0.25,
    bottomRadius: topRadius * 0.25 + bottomRadius * 0.75,
    height: height / 2,
    angle: Math.PI
  }, 0)

  const tagInner = generateTag({
    gap: 1,
    topRadius: topRadius * 0.75 + bottomRadius * 0.25,
    bottomRadius: topRadius * 0.25 + bottomRadius * 0.75,
    height: height / 2,
    angle: Math.PI
  }, 0.1)

  let tagPoints = [...tagInner.points, ...tagOuter.points];

  let tagOuterIndex = [...tagOuter.indices]
  tagOuterIndex.forEach((value, index) => {
    tagOuterIndex[index] += tagInner.points.length;
  });
  let tagIndex = [...tagInner.indices, ...tagOuterIndex];

  for(let i=0; i<ROTATESEGMENTS-2; i++) {
    let leftTop = i * tagInner.row + tagInner.row-1;
    let leftBottom = i * tagOuter.row + tagOuter.row-1 + tagInner.points.length;
    let rightTop = leftTop + tagInner.row;
    let rightBottom = leftBottom + tagOuter.row;
    if(i===ROTATESEGMENTS-2) {
      rightTop = tagInner.row-1;
      rightBottom = tagOuter.row-1 + tagInner.points.length
    }

    // let leftBottom = i * eachColumn + eachColumn-1;
    // let leftTop = leftBottom + fin_points.length;
    // let rightBottom = leftBottom + eachColumn;
    // if(i===ROTATESEGMENTS-2) {
    //   rightBottom = eachColumn-1;
    // }
    // let rightTop = rightBottom + fin_points.length;
    tagIndex.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
  }

  let tagGeometry = new BufferGeometry().setFromPoints(tagPoints);

  if(!CURVEONLY) {
    tagGeometry.setIndex(new BufferAttribute(new Uint16Array(tagIndex), 1))
    tagGeometry.computeVertexNormals();
  }

  let tagMesh;
  if(!CURVEONLY) {
    tagMesh = new Mesh(
      tagGeometry,
      new MeshPhysicalMaterial(
        {
          envMap: engine.envMap,
          side: DoubleSide,
          wireframe: false,
          roughness: 0.5,
          color: 0xff0000
        }
      )
    );
  } else {
    tagMesh = new Line(
      tagGeometry,
      new LineBasicMaterial()
    );
  }
  tagMesh.position.y = height * 0.5;

  let threadMesh;
  let threadRounds = 1.5;
  let threadHeightRatio = 0.5;
  let crestWidth = neckRadius * 0.125;
  let crestHeight = neckRadius * 0.086;

  const capThickness = 2;
  const capParams = {
    radius: neckRadius + 0.5 + capThickness + crestHeight,
    neckCorner: 5,
    height: neckHeight -2
  }
  const capOuter = generateBottleCapBody(capParams, 0);
  const capInner = generateBottleCapBody(capParams, capThickness);
  points = [...capInner.points, ...capOuter.points];

  outerIndex = [...capOuter.indices]
  outerIndex.forEach((value, index) => {
    outerIndex[index] += capInner.points.length;
  });
  index = [...capInner.indices, ...outerIndex];

  for(let i=0; i<ROTATESEGMENTS-1; i++) {
    let leftTop = i * capInner.row;
    let leftBottom = i * capOuter.row + capInner.points.length;
    let rightTop = leftTop + capInner.row;
    let rightBottom = leftBottom + capOuter.row;
    if(i===ROTATESEGMENTS-2) {
      rightTop = 0;
      rightBottom = 0 + capInner.points.length
    }
    index.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
  }

  geometry = new BufferGeometry().setFromPoints(points);

  if(!CURVEONLY) {
    geometry.setIndex(new BufferAttribute(new Uint16Array(index), 1))
    geometry.computeVertexNormals();
  }

  let capMesh;
  if(!CURVEONLY) {
    capMesh = new Mesh(
      geometry,
      new MeshPhysicalMaterial(
        {
          envMap: engine.envMap,
          side: DoubleSide,
          wireframe: false,
          color: 0x227732
        }
      )
    );
  } else {
    capMesh = new Line(
      geometry,
      new LineBasicMaterial()
    );
  }

  const group = new Group();
  capMesh.position.y = height + neckHeight - capParams.height + capParams.neckCorner;
  group.add(capMesh)
  group.add(tagMesh)

  let threadRes = createThread({
    crestWidth: crestWidth,
    pitch: neckHeight * threadHeightRatio / threadRounds,
    rounds: threadRounds,
    radius: neckRadius,
    angle: 60,
    crestHeight: crestHeight
  });
  const threadGeo = new BufferGeometry().setFromPoints(threadRes.points);
  if(!CURVEONLY) {
    threadGeo.setIndex(new BufferAttribute(new Uint16Array(threadRes.indices), 1))
    threadGeo.computeVertexNormals();
    threadMesh = new Mesh(
      threadGeo,
      new MeshPhysicalMaterial(
        {
          envMap: engine.envMap,
          side: DoubleSide,
          wireframe: false,
          color:223399,
          roughness: 0,
          transmission: 1
        }
      )
    );
  } else {
    threadMesh = new Line(
      threadGeo,
      new LineBasicMaterial()
    );
  }
  threadMesh.position.y = height + (1-threadHeightRatio)*0.5*neckHeight;

  // inner thread

  let innerThreadMesh;
  threadRes = createInnerThread({
    crestWidth: crestWidth,
    pitch: neckHeight * threadHeightRatio / threadRounds,
    rounds: threadRounds,
    radius: neckRadius,
    angle: 60,
    crestHeight: crestHeight
  });
  const innerThreadGeo = new BufferGeometry().setFromPoints(threadRes.points);
  if(!CURVEONLY) {
    innerThreadGeo.setIndex(new BufferAttribute(new Uint16Array(threadRes.indices), 1))
    innerThreadGeo.computeVertexNormals();
    innerThreadMesh = new Mesh(
      innerThreadGeo,
      new MeshPhysicalMaterial(
        {
          envMap: engine.envMap,
          side: DoubleSide,
          wireframe: false
        }
      )
    );
  } else {
    innerThreadMesh = new Line(
      innerThreadGeo,
      new LineBasicMaterial()
    );
  }

  innerThreadMesh.position.y = height + (1-threadHeightRatio)*0.5*neckHeight + neckHeight * threadHeightRatio / threadRounds * 0.5;
  // innerThreadMesh.position.y = height + (1-threadHeightRatio)*0.5*neckHeight;
  const bottleGroup = new Group();
  bottleGroup.add(bottleMesh);
  bottleGroup.add(threadMesh);
  const capGroup = new Group();
  capGroup.add(innerThreadMesh);
  capGroup.add(capMesh);
  group.add(bottleGroup);
  group.add(capGroup);
  console.log(bottleGroup, 'bottleGroup');
  console.log(capGroup, 'capGroup');

  // bottleInner.position.y = bottleThickness;
  // group.add(cap);
  // group.add(mesh);
  // group.add(bottleOuter);
  if(engine.object) {
    engine.scene.remove(engine.object)
  }
  engine.scene.add(group);
  engine.object = group;
}

console.log(changeBottle)

function drawDimensionLine(two, point1, point2, offset, value, options = {}) {
    // 配置选项
    const config = {
        arrowSize: options.arrowSize || 8,
        minInnerDistance: options.minInnerDistance || 30,
        textOffset: options.textOffset || 8,
        lineColor: options.lineColor || '#000',
        lineWidth: options.lineWidth || 1,
        extensionColor: options.extensionColor || '#666',
        extensionWidth: options.extensionWidth || 0.5,
        textColor: options.textColor || '#000',
        textSize: options.textSize || 12,
        editable: options.editable !== false, // 默认可编辑
        onValueChange: options.onValueChange || null, // 值改变的回调
        ...options
    };
    
    // 1-6. 前面的代码保持不变...
    const dx = point2.x - point1.x;
    const dy = point2.y - point1.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    
    if (length === 0) return null;
    
    const unitX = dx / length;
    const unitY = dy / length;
    const normalX = -unitY;
    const normalY = unitX;
    
    // 计算尺寸线的角度（弧度）
    const lineAngle = Math.atan2(dy, dx);
    const lineAngleDeg = (lineAngle * 180 / Math.PI + 360) % 360; // 转换为0-360度
    
    const offsetStart = {
        x: point1.x + normalX * offset,
        y: point1.y + normalY * offset
    };
    const offsetEnd = {
        x: point2.x + normalX * offset,
        y: point2.y + normalY * offset
    };
    
    const dimensionLine = two.makeLine(
        offsetStart.x, offsetStart.y, 
        offsetEnd.x, offsetEnd.y
    );
    dimensionLine.stroke = config.lineColor;
    dimensionLine.linewidth = config.lineWidth;
    
    const extension1 = two.makeLine(
        point1.x, point1.y, 
        offsetStart.x, offsetStart.y
    );
    const extension2 = two.makeLine(
        point2.x, point2.y, 
        offsetEnd.x, offsetEnd.y
    );
    extension1.stroke = extension2.stroke = config.extensionColor;
    extension1.linewidth = extension2.linewidth = config.extensionWidth;
    
    // 7. 判断是否需要外部箭头
    const useOuterArrows = length < config.minInnerDistance;
    let arrows = [];
    
    if (useOuterArrows) {
        arrows = drawOuterArrows(two, offsetStart, offsetEnd, config.arrowSize, config.lineColor);
        
        const extensionLength = config.arrowSize + 5;
        const extendedStart = {
            x: offsetStart.x - unitX * extensionLength,
            y: offsetStart.y - unitY * extensionLength
        };
        const extendedEnd = {
            x: offsetEnd.x + unitX * extensionLength,
            y: offsetEnd.y + unitY * extensionLength
        };
        
        const extensionLine1 = two.makeLine(
            offsetStart.x, offsetStart.y,
            extendedStart.x, extendedStart.y
        );
        const extensionLine2 = two.makeLine(
            offsetEnd.x, offsetEnd.y,
            extendedEnd.x, extendedEnd.y
        );
        
        extensionLine1.stroke = extensionLine2.stroke = config.extensionColor;
        extensionLine1.linewidth = extensionLine2.linewidth = config.extensionWidth;
        
        arrows.push(extensionLine1, extensionLine2);
    } else {
        arrows = drawInnerArrows(two, offsetStart, offsetEnd, config.arrowSize, config.lineColor);
    }
    
    // 8. 智能文本定位和旋转
    const midPoint = {
        x: (offsetStart.x + offsetEnd.x) / 2,
        y: (offsetStart.y + offsetEnd.y) / 2
    };
    
    const textInfo = calculateTextPositionAndRotation(
        midPoint, 
        lineAngleDeg, 
        offset, 
        normalX, 
        normalY, 
        config.textOffset
    );
    
    let currentValue = value;
    const text = two.makeText(
        currentValue.toString(), 
        textInfo.x, 
        textInfo.y
    );
    text.fill = config.textColor;
    text.size = config.textSize;
    text.alignment = 'center';
    
    // 应用旋转
    if (textInfo.rotation !== 0) {
        text.rotation = textInfo.rotation;
    }
    
    // 创建返回对象，包含编辑功能
    const dimensionAnnotation = {
        dimensionLine,
        extension1,
        extension2,
        text,
        arrows,
        isOuterArrows: useOuterArrows,
        textRotation: textInfo.rotation,
        currentValue,
        // 添加编辑相关方法
        makeEditable: function() {
            if (config.editable) {
                addDimensionTextEditInteraction(two, this, config);
            }
        },
        updateValue: function(newValue) {
            this.currentValue = newValue;
            this.text.value = newValue.toString();
            two.update();
            
            // 触发回调
            if (config.onValueChange) {
                config.onValueChange(newValue, this);
            }
        }
    };
    
    // 自动启用编辑功能
    if (config.editable) {
        dimensionAnnotation.makeEditable();
    }
    
    return dimensionAnnotation;
}

// 添加尺寸文本编辑交互
function addDimensionTextEditInteraction(two, dimensionAnnotation, config) {
    const canvas = two.renderer.domElement;
    const text = dimensionAnnotation.text;
    
    // 监听点击事件
    canvas.addEventListener('click', function(event) {
        const rect = canvas.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const clickY = event.clientY - rect.top;
        
        // 转换为画布坐标（考虑Y轴翻转）
        let canvasX = clickX;
        let canvasY = clickY;
        
        if (two._yAxisUp) {
            canvasY = two.height - clickY;
        }
        
        // 检查点击是否在文字附近
        const textBounds = getDimensionTextBounds(text, canvasX, canvasY);
        
        if (isPointInDimensionTextBounds(canvasX, canvasY, textBounds)) {
            showDimensionTextEditor(two, dimensionAnnotation, config, event.clientX, event.clientY);
        }
    });
}

// 计算尺寸文字边界框
function getDimensionTextBounds(textObj, centerX, centerY) {
    const fontSize = textObj.size || 12;
    const textLength = textObj.value.length;
    const approximateWidth = textLength * fontSize * 0.6;
    const approximateHeight = fontSize * 1.2;
    
    // 获取实际位置
    const actualX = textObj.translation.x;
    const actualY = textObj.translation.y;
    
    // 考虑旋转的影响，扩大点击区域
    const padding = fontSize * 0.5;
    
    return {
        left: actualX - approximateWidth / 2 - padding,
        right: actualX + approximateWidth / 2 + padding,
        top: actualY - approximateHeight / 2 - padding,
        bottom: actualY + approximateHeight / 2 + padding
    };
}

// 检查点是否在尺寸文字边界框内
function isPointInDimensionTextBounds(x, y, bounds) {
    return x >= bounds.left && x <= bounds.right && 
           y >= bounds.top && y <= bounds.bottom;
}

// 显示尺寸文字编辑器
function showDimensionTextEditor(two, dimensionAnnotation, config, screenX, screenY) {
    // 创建输入框
    const input = document.createElement('input');
    input.type = 'text';
    input.value = dimensionAnnotation.currentValue.toString();
    input.style.position = 'fixed';
    input.style.left = screenX + 'px';
    input.style.top = screenY + 'px';
    input.style.zIndex = '9999';
    input.style.padding = '4px 8px';
    input.style.border = '2px solid #007acc';
    input.style.borderRadius = '4px';
    input.style.fontSize = config.textSize + 'px';
    input.style.fontFamily = 'Arial, sans-serif';
    input.style.outline = 'none';
    input.style.background = '#fff';
    input.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
    
    document.body.appendChild(input);
    input.focus();
    input.select();
    
    // 处理确认输入
    function confirmEdit() {
        const newValue = input.value.trim();
        
        if (newValue !== '') {
            dimensionAnnotation.updateValue(newValue);
        } else {
            alert('请输入有效的尺寸值');
            return;
        }
        
        document.body.removeChild(input);
    }
    
    // 处理取消输入
    function cancelEdit() {
        document.body.removeChild(input);
    }
    
    // 监听按键事件
    input.addEventListener('keydown', function(event) {
        event.stopPropagation();
        
        if (event.key === 'Enter') {
            confirmEdit();
        } else if (event.key === 'Escape') {
            cancelEdit();
        }
    });
    
    // 监听失去焦点事件
    input.addEventListener('blur', function() {
        setTimeout(() => {
            if (document.body.contains(input)) {
                confirmEdit();
            }
        }, 100);
    });
    
    // 阻止事件冒泡
    input.addEventListener('click', function(event) {
        event.stopPropagation();
    });
}

// 计算文本位置和旋转角度 - 保持不变
function calculateTextPositionAndRotation(midPoint, angleInDegrees, offset, normalX, normalY, textOffset) {
    const angle = (angleInDegrees + 360) % 360;
    
    let textX = midPoint.x;
    let textY = midPoint.y;
    let rotation = 0;
    
    if (isHorizontalRange(angle)) {
        const textOffsetDirection = Math.sign(offset);
        textX = midPoint.x;
        textY = midPoint.y + normalY * textOffset * textOffsetDirection;
        rotation = 0;
        
    } else if (isVerticalRange(angle)) {
        if (angle >= 60 && angle <= 120) {
            textX = midPoint.x + textOffset;
            rotation = Math.PI / 2;
        } else {
            textX = midPoint.x + textOffset;
            rotation = -Math.PI / 2;
        }
        
        textY = midPoint.y;
        
    } else {
        const textOffsetDirection = Math.sign(offset);
        textX = midPoint.x + normalX * textOffset * textOffsetDirection;
        textY = midPoint.y + normalY * textOffset * textOffsetDirection;
        
        let textAngle = angleInDegrees * Math.PI / 180;
        
        if (angle > 90 && angle < 270) {
            textAngle += Math.PI;
        }
        
        rotation = textAngle;
    }
    
    return {
        x: textX,
        y: textY,
        rotation: rotation
    };
}

// 判断是否在水平范围内 - 保持不变
function isHorizontalRange(angle) {
    return (angle >= 0 && angle <= 30) || 
           (angle >= 330 && angle <= 360) || 
           (angle >= 150 && angle <= 210);
}

// 判断是否在垂直范围内 - 保持不变
function isVerticalRange(angle) {
    return (angle >= 60 && angle <= 120) || 
           (angle >= 240 && angle <= 300);
}

// 其他函数保持不变...
function drawInnerArrows(two, start, end, arrowSize, color) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    
    if (length === 0) return [];
    
    const unitX = dx / length;
    const unitY = dy / length;
    
    const arrows = [];
    
    // 左箭头（指向右）
    const leftArrow = two.makePath([
        new Two.Vector(start.x, start.y),
        new Two.Vector(
            start.x + arrowSize * unitX + arrowSize * 0.4 * unitY,
            start.y + arrowSize * unitY - arrowSize * 0.4 * unitX
        ),
        new Two.Vector(
            start.x + arrowSize * unitX - arrowSize * 0.4 * unitY,
            start.y + arrowSize * unitY + arrowSize * 0.4 * unitX
        )
    ]);
    leftArrow.closed = true;
    leftArrow.fill = color;
    leftArrow.noStroke();
    
    // 右箭头（指向左）
    const rightArrow = two.makePath([
        new Two.Vector(end.x, end.y),
        new Two.Vector(
            end.x - arrowSize * unitX + arrowSize * 0.4 * unitY,
            end.y - arrowSize * unitY - arrowSize * 0.4 * unitX
        ),
        new Two.Vector(
            end.x - arrowSize * unitX - arrowSize * 0.4 * unitY,
            end.y - arrowSize * unitY + arrowSize * 0.4 * unitX
        )
    ]);
    rightArrow.closed = true;
    rightArrow.fill = color;
    rightArrow.noStroke();
    
    arrows.push(leftArrow, rightArrow);
    return arrows;
}

function drawOuterArrows(two, start, end, arrowSize, color) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    
    if (length === 0) return [];
    
    const unitX = dx / length;
    const unitY = dy / length;
    
    const arrows = [];
    
    // 左箭头：箭头尖端在标注线起点，指向标注线内部
    const leftArrowBase = {
        x: start.x - arrowSize * unitX,
        y: start.y - arrowSize * unitY
    };
    
    const leftArrow = two.makePath([
        new Two.Vector(start.x, start.y),
        new Two.Vector(
            leftArrowBase.x + arrowSize * 0.4 * unitY,
            leftArrowBase.y - arrowSize * 0.4 * unitX
        ),
        new Two.Vector(
            leftArrowBase.x - arrowSize * 0.4 * unitY,
            leftArrowBase.y + arrowSize * 0.4 * unitX
        )
    ]);
    leftArrow.closed = true;
    leftArrow.fill = color;
    leftArrow.noStroke();
    
    // 右箭头：箭头尖端在标注线终点，指向标注线内部
    const rightArrowBase = {
        x: end.x + arrowSize * unitX,
        y: end.y + arrowSize * unitY
    };
    
    const rightArrow = two.makePath([
        new Two.Vector(end.x, end.y),
        new Two.Vector(
            rightArrowBase.x + arrowSize * 0.4 * unitY,
            rightArrowBase.y - arrowSize * 0.4 * unitX
        ),
        new Two.Vector(
            rightArrowBase.x - arrowSize * 0.4 * unitY,
            rightArrowBase.y + arrowSize * 0.4 * unitX
        )
    ]);
    rightArrow.closed = true;
    rightArrow.fill = color;
    rightArrow.noStroke();
    
    arrows.push(leftArrow, rightArrow);
    return arrows;
}


function drawRadiusAnnotation(two, centerPoint, pointOnCircle, radius, options = {}) {
    // 配置选项
    const config = {
        arrowSize: options.arrowSize || 8,
        arrowLength: options.arrowLength || 40,
        lineColor: options.lineColor || '#000',
        lineWidth: options.lineWidth || 1,
        textColor: options.textColor || '#000',
        textSize: options.textSize || 12,
        textOffset: options.textOffset || 8,
        showRadiusSymbol: options.showRadiusSymbol !== false,
        editable: options.editable !== false, // 默认可编辑
        onValueChange: options.onValueChange || null, // 值改变的回调
        ...options
    };
    
    let arrowDirection, arrowStart, arrowEnd, textPosition;
    
    // 处理半径为0的特殊情况
    if (radius === 0) {
        arrowStart = pointOnCircle;
        arrowEnd = {
            x: pointOnCircle.x - config.arrowLength,
            y: pointOnCircle.y
        };
        arrowDirection = { x: -1, y: 0 };
        
        textPosition = {
            x: arrowEnd.x - config.textOffset,
            y: arrowEnd.y
        };
    } else {
        const dx = centerPoint.x - pointOnCircle.x;
        const dy = centerPoint.y - pointOnCircle.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        if (distance === 0) {
            console.warn('圆心和圆上的点重合');
            return null;
        }
        
        const unitX = dx / distance;
        const unitY = dy / distance;
        arrowDirection = { x: unitX, y: unitY };
        
        arrowStart = pointOnCircle;
        arrowEnd = {
            x: pointOnCircle.x - unitX * config.arrowLength,
            y: pointOnCircle.y - unitY * config.arrowLength
        };
        
        textPosition = {
            x: arrowEnd.x - unitX * config.textOffset,
            y: arrowEnd.y - unitY * config.textOffset
        };
    }
    
    // 绘制箭头线
    const arrowLine = two.makeLine(
        arrowStart.x, arrowStart.y,
        arrowEnd.x, arrowEnd.y
    );
    arrowLine.stroke = config.lineColor;
    arrowLine.linewidth = config.lineWidth;
    
    // 绘制箭头头部
    const arrowHead = createArrowHead(
        two, 
        arrowStart, 
        arrowDirection, 
        config.arrowSize, 
        config.lineColor
    );
    
    // 准备文字内容
    let currentValue = radius;
    const textContent = config.showRadiusSymbol ? `R${currentValue}` : currentValue.toString();
    
    // 绘制文字
    const text = two.makeText(
        textContent,
        textPosition.x,
        textPosition.y
    );
    text.fill = config.textColor;
    text.size = config.textSize;
    text.alignment = 'center';
    
    // 可选：绘制辅助的半径线
    let radiusLine = null;
    if (options.showRadiusLine && radius > 0) {
        radiusLine = two.makeLine(
            centerPoint.x, centerPoint.y,
            pointOnCircle.x, pointOnCircle.y
        );
        radiusLine.stroke = options.radiusLineColor || '#ccc';
        radiusLine.linewidth = options.radiusLineWidth || 0.5;
        radiusLine.dashes = [3, 3];
    }
    
    // 创建交互功能
    const annotation = {
        arrowLine,
        arrowHead,
        text,
        radiusLine,
        isZeroRadius: radius === 0,
        currentValue,
        // 添加交互方法
        makeEditable: function() {
            if (config.editable) {
                addTextEditInteraction(two, this, config);
            }
        },
        updateValue: function(newValue) {
            this.currentValue = newValue;
            const newTextContent = config.showRadiusSymbol ? `R${newValue}` : newValue.toString();
            this.text.value = newTextContent;
            two.update();
            
            // 触发回调
            if (config.onValueChange) {
                config.onValueChange(newValue, this);
            }
        }
    };
    
    // 自动启用编辑功能
    if (config.editable) {
        annotation.makeEditable();
    }
    
    return annotation;
}

// 添加文字编辑交互
function addTextEditInteraction(two, annotation, config) {
    const canvas = two.renderer.domElement;
    const text = annotation.text;
    
    // 添加鼠标样式提示
    text.cursor = 'pointer';
    
    // 监听点击事件
    canvas.addEventListener('click', function(event) {
        const rect = canvas.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const clickY = event.clientY - rect.top;
        
        // 转换为画布坐标（考虑Y轴翻转）
        let canvasX = clickX;
        let canvasY = clickY;
        
        if (two._yAxisUp) {
            canvasY = two.height - clickY;
        }
        
        // 检查点击是否在文字附近
        const textBounds = getTextBounds(text, canvasX, canvasY);
        
        if (isPointInBounds(canvasX, canvasY, textBounds)) {
            showTextEditor(two, annotation, config, event.clientX, event.clientY);
        }
    });
}

// 计算文字边界框
function getTextBounds(textObj, centerX, centerY) {
    const fontSize = textObj.size || 12;
    const textLength = textObj.value.length;
    const approximateWidth = textLength * fontSize * 0.6; // 粗略估算
    const approximateHeight = fontSize * 1.2;
    
    // 获取实际位置
    const actualX = textObj.translation.x;
    const actualY = textObj.translation.y;
    
    return {
        left: actualX - approximateWidth / 2,
        right: actualX + approximateWidth / 2,
        top: actualY - approximateHeight / 2,
        bottom: actualY + approximateHeight / 2
    };
}

// 检查点是否在边界框内
function isPointInBounds(x, y, bounds) {
    return x >= bounds.left && x <= bounds.right && 
           y >= bounds.top && y <= bounds.bottom;
}

// 显示文字编辑器
function showTextEditor(two, annotation, config, screenX, screenY) {
    // 创建输入框
    const input = document.createElement('input');
    input.type = 'text';
    input.value = annotation.currentValue.toString();
    input.style.position = 'fixed';
    input.style.left = screenX + 'px';
    input.style.top = screenY + 'px';
    input.style.zIndex = '9999';
    input.style.padding = '4px 8px';
    input.style.border = '2px solid #007acc';
    input.style.borderRadius = '4px';
    input.style.fontSize = config.textSize + 'px';
    input.style.fontFamily = 'Arial, sans-serif';
    input.style.outline = 'none';
    input.style.background = '#fff';
    input.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
    
    document.body.appendChild(input);
    input.focus();
    input.select();
    
    // 处理确认输入
    function confirmEdit() {
        const newValue = parseFloat(input.value);
        
        if (!isNaN(newValue) && newValue >= 0) {
            annotation.updateValue(newValue);
        } else {
            alert('请输入有效的数字值（≥0）');
            return;
        }
        
        document.body.removeChild(input);
    }
    
    // 处理取消输入
    function cancelEdit() {
        document.body.removeChild(input);
    }
    
    // 监听按键事件
    input.addEventListener('keydown', function(event) {
        event.stopPropagation();
        
        if (event.key === 'Enter') {
            confirmEdit();
        } else if (event.key === 'Escape') {
            cancelEdit();
        }
    });
    
    // 监听失去焦点事件
    input.addEventListener('blur', function() {
        setTimeout(() => {
            if (document.body.contains(input)) {
                confirmEdit();
            }
        }, 100);
    });
    
    // 阻止事件冒泡
    input.addEventListener('click', function(event) {
        event.stopPropagation();
    });
}

// 创建箭头头部（保持不变）
function createArrowHead(two, tipPoint, direction, arrowSize, color) {
    const normalX = -direction.y;
    const normalY = direction.x;
    
    const arrowHead = two.makePath([
        new Two.Vector(tipPoint.x, tipPoint.y),
        new Two.Vector(
            tipPoint.x - direction.x * arrowSize + normalX * arrowSize * 0.4,
            tipPoint.y - direction.y * arrowSize + normalY * arrowSize * 0.4
        ),
        new Two.Vector(
            tipPoint.x - direction.x * arrowSize - normalX * arrowSize * 0.4,
            tipPoint.y - direction.y * arrowSize - normalY * arrowSize * 0.4
        )
    ]);
    
    arrowHead.closed = true;
    arrowHead.fill = color;
    arrowHead.noStroke();
    
    return arrowHead;
}



const onResize = () => {
  const width = container.value.offsetWidth;
  const height = container.value.offsetHeight;
  engine.renderer.setSize(width, height);
  engine.camera.aspect = width / height;
  engine.camera.updateProjectionMatrix();
}

const setupEnv = async () => {
  engine.renderer = new WebGLRenderer();
  engine.scene = new Scene();
  engine.scene.background = new Color(1,1,1);
  engine.camera = new PerspectiveCamera();
  engine.camera.near = 0.01;
  engine.camera.far = 5000;
  engine.orbit = new OrbitControls(engine.camera, engine.renderer.domElement);
  container.value.appendChild(engine.renderer.domElement);

  const envMap = await new RGBELoader().loadAsync("/public/rect.hdr");
  envMap.mapping = EquirectangularReflectionMapping;
  engine.envMap = envMap;


  const grid = new GridHelper(400, 20);
  engine.scene.add(grid);

  engine.camera.position.set(10, 10, 10);
  engine.camera.lookAt(0, 0, 0);
  onResize();

  const container2D = two.value;
  engineTwo.two = new Two({
    width: container2D.clientWidth,
    height: container2D.clientHeight
  }).appendTo(container2D);
  console.log(engineTwo.two)
  engineTwo.value = new Engine2D(container2D);
  // engineTwo.two.scene._matrix.manual = true;
  // engineTwo.two.scene._matrix.translate(0, engineTwo.two.height).scale(1, -1);
  // engineTwo.two.renderer.domElement.style.background = "#ffffff";
  
  render();

  setObjects(engineTwo.value);
}

const createInnerThread = (params) => {
  const THREAD_SEGMENTS = 10;
  const {crestWidth, pitch, rounds, radius, angle, crestHeight } = params
  let angle_rad = angle / 180 * Math.PI;
  // 牙宽 45°
  const A = new Vector3();
  const B = new Vector3(-crestHeight, crestHeight/Math.tan(angle_rad), 0);
  const C = new Vector3(-crestHeight, crestWidth - crestHeight/Math.tan(angle_rad), 0);
  const D = new Vector3(0, crestWidth, 0);
  const corner = 0.15;
  const roundResB = roundCorner(A, B, C, corner);
  console.log(roundResB.round.angle*180/Math.PI);
  const O1_B = roundResB.oc;
  const roundResC = roundCorner(O1_B, C, D, corner);
  const points = [];
  const A_O1_A = new LineCurve3(A, roundResB.oa)
  points.push(...A_O1_A.getPoints(THREAD_SEGMENTS));

  const originCenter = A.clone().add(D).multiplyScalar(0.5);

  let axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  let axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  let axis = axis_0.clone().cross(axis_1).normalize();

  let rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResB.round.angle/(THREAD_SEGMENTS-1));
  let dir = axis_0.clone();
  points.pop();
  for(let i=0; i< THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o.clone().add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

 


  const O1_B_O2_C = new LineCurve3(roundResB.oc, roundResC.oa)
  points.pop();
  points.push(...O1_B_O2_C.getPoints(THREAD_SEGMENTS));

  axis_0 = roundResC.oa.clone().sub(roundResC.round.o).normalize();
  axis_1 = roundResC.oc.clone().sub(roundResC.round.o).normalize();
  axis = axis_0.clone().cross(axis_1);
  

  rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResC.round.angle/(THREAD_SEGMENTS-1));
  dir = axis_0.clone();
  points.pop();
  for(let i=0; i< THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResC.round.o.clone().add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

  const O2_C_D = new LineCurve3(roundResC.oc, D)
  points.pop();
  points.push(...O2_C_D.getPoints(THREAD_SEGMENTS));

  points.forEach(point => {
    point.x += radius + crestHeight;
  })

  originCenter.x += radius + crestHeight;

  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach(point => {
    if(prev) {
      const dist = point.distanceTo(prev);
      if(dist > 1e-6) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });

  const totalPoints = [];

  let totalSteps = ROTATESEGMENTS * rounds;
  totalSteps = Math.ceil(totalSteps)
  const rotate_step = Math.PI * 2 * rounds / (totalSteps - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), rotate_step);
  let rotated_points = null;
  const indices = [];
  let originCenterCopy = originCenter.clone();
  if(!CURVEONLY) {
    for(let i=0; i<totalSteps; i++) {
      if(rotated_points) {
        originCenterCopy.applyQuaternion(rotateQuat);
        let origin_points = rotated_points;
        rotated_points = rotated_points.map(point => {
          return point.clone().applyQuaternion(rotateQuat);
        });
        for(let j=1; j<origin_points.length; j++) {
          const leftTop = (i-1) * origin_points.length + j-1;
          const leftBottom = (i-1) * origin_points.length + j;
          const rightTop = i * origin_points.length + j-1;
          const rightBottom = i * origin_points.length + j;
          indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        }
      } else {
        rotated_points = f_points;
      }
      totalPoints.push(rotated_points)
    }
  } else {
    totalPoints.push(f_points)
  }


  if(!CURVEONLY) {
    totalPoints.forEach((points, idx) => {
      points.forEach(point => {
        point.y += idx * rounds * pitch / totalSteps
      })
    })
  }

  originCenterCopy.y += rounds * pitch;
  totalPoints.push([originCenter, originCenterCopy]);

  const fin_points = totalPoints.flatMap(points => [...points]);

  const originIndex = fin_points.length - 2;
  const originCopyIndex = fin_points.length - 1;


  for(let j=1; j<rotated_points.length; j++) {
    const o1 = originIndex;
    const a1 = j-1;
    const b1 = j;
    indices.push(o1, b1, a1);

    const o2 = originCopyIndex;
    const a2 = a1 + rotated_points.length * (totalSteps -1);
    const b2 = b1 + rotated_points.length * (totalSteps -1);
    indices.push(o2, b2, a2);

  }



  const data = {
    indices,
    points: fin_points,
    row: f_points.length
  }

  return data;

}

const createThread = (params) => {
  const THREAD_SEGMENTS = 10;
  const {crestWidth, pitch, rounds, radius, angle, crestHeight } = params
  let angle_rad = angle / 180 * Math.PI;
  // 牙宽 45°
  const A = new Vector3();
  const B = new Vector3(crestHeight, crestHeight/Math.tan(angle_rad), 0);
  const C = new Vector3(crestHeight, crestWidth - crestHeight/Math.tan(angle_rad), 0);
  const D = new Vector3(0, crestWidth, 0);
  const corner = 0.15;
  const roundResB = roundCorner(A, B, C, corner);
  console.log(roundResB.round.angle*180/Math.PI);
  const O1_B = roundResB.oc;
  const roundResC = roundCorner(O1_B, C, D, corner);
  const points = [];
  const A_O1_A = new LineCurve3(A, roundResB.oa)
  points.push(...A_O1_A.getPoints(THREAD_SEGMENTS));

  const originCenter = A.clone().add(D).multiplyScalar(0.5);

  let axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  let axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  let axis = axis_0.clone().cross(axis_1).normalize();

  let rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResB.round.angle/(THREAD_SEGMENTS-1));
  let dir = axis_0.clone();
  points.pop();
  for(let i=0; i< THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o.clone().add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

 


  const O1_B_O2_C = new LineCurve3(roundResB.oc, roundResC.oa)
  points.pop();
  points.push(...O1_B_O2_C.getPoints(THREAD_SEGMENTS));

  axis_0 = roundResC.oa.clone().sub(roundResC.round.o).normalize();
  axis_1 = roundResC.oc.clone().sub(roundResC.round.o).normalize();
  axis = axis_0.clone().cross(axis_1);
  

  rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResC.round.angle/(THREAD_SEGMENTS-1));
  dir = axis_0.clone();
  points.pop();
  for(let i=0; i< THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResC.round.o.clone().add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

  const O2_C_D = new LineCurve3(roundResC.oc, D)
  points.pop();
  points.push(...O2_C_D.getPoints(THREAD_SEGMENTS));

  points.forEach(point => {
    point.x += radius;
  })

  originCenter.x += radius;

  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach(point => {
    if(prev) {
      const dist = point.distanceTo(prev);
      if(dist > 1e-6) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });

  const totalPoints = [];

  let totalSteps = ROTATESEGMENTS * rounds;
  totalSteps = Math.ceil(totalSteps)
  const rotate_step = Math.PI * 2 * rounds / (totalSteps - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), rotate_step);
  let rotated_points = null;
  const indices = [];
  let originCenterCopy = originCenter.clone();
  if(!CURVEONLY) {
    for(let i=0; i<totalSteps; i++) {
      if(rotated_points) {
        originCenterCopy.applyQuaternion(rotateQuat);
        let origin_points = rotated_points;
        rotated_points = rotated_points.map(point => {
          return point.clone().applyQuaternion(rotateQuat);
        });
        // indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        for(let j=1; j<origin_points.length; j++) {
          const leftTop = (i-1) * origin_points.length + j-1;
          const leftBottom = (i-1) * origin_points.length + j;
          const rightTop = i * origin_points.length + j-1;
          const rightBottom = i * origin_points.length + j;
          indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
        }
      } else {
        rotated_points = f_points;
      }
      totalPoints.push(rotated_points)
    }
  } else {
    totalPoints.push(f_points)
  }

  // if(!CURVEONLY) {
  //   console.log(totalPoints)
  //   for(let i=0; i<rounds; i++) {
  //     for(let j=0; j<ROTATESEGMENTS;j++) {
  //       totalPoints[i*ROTATESEGMENTS + j].forEach(point => {
  //         point.y += i*pitch + j/ROTATESEGMENTS * pitch
  //       })
        
  //     }
  //   }
  // }

  if(!CURVEONLY) {
    console.log(totalPoints)
    // for(let i=0; i<rounds; i++) {
    //   for(let j=0; j<ROTATESEGMENTS;j++) {
    //     totalPoints[i*ROTATESEGMENTS + j].forEach(point => {
    //       point.y += i*pitch + j/ROTATESEGMENTS * pitch
    //     })
        
    //   }
    // }
    totalPoints.forEach((points, idx) => {
      points.forEach(point => {
        point.y += idx * rounds * pitch / totalSteps
      })
    })
  }

  originCenterCopy.y += rounds * pitch;
  totalPoints.push([originCenter, originCenterCopy]);

  const fin_points = totalPoints.flatMap(points => [...points]);

  const originIndex = fin_points.length - 2;
  const originCopyIndex = fin_points.length - 1;


  for(let j=1; j<rotated_points.length; j++) {
    const o1 = originIndex;
    const a1 = j-1;
    const b1 = j;
    indices.push(o1, b1, a1);

    const o2 = originCopyIndex;
    const a2 = a1 + rotated_points.length * (totalSteps -1);
    const b2 = b1 + rotated_points.length * (totalSteps -1);
    indices.push(o2, b2, a2);

  }



  const data = {
    indices,
    points: fin_points,
    row: f_points.length
  }

  return data;

}

const setObjects = () => {
  changeBottle(engineTwo.value, engine);
  console.log(changeBottle)
}

const render = () => {
  engine.orbit.update();
  engine.renderer.render(engine.scene, engine.camera);
  engineTwo.value.onUpdate();
  // engineTwo.two.update()
  requestAnimationFrame(render);
}


</script>

<template>
  <div ref="container" id="container">
    <div ref="two" id="two"></div>
  </div>
</template>

<style scoped>

#container{
  width: 100%;
  height: 100%;
  position: relative;
}

#two {
  width: 500px;
  height: 500px;
  position: absolute;
  background: #ffffff;
  left: 0;
  top:0
}

</style>
