<script setup>
import { ArcCurve, BoxGeometry, BufferAttribute, BufferGeometry, CatmullRomCurve3, DoubleSide, EquirectangularReflectionMapping, GridHelper, Group, Line, Line3, LineBasicMaterial, LineCurve3, Mesh, MeshPhysicalMaterial, PerspectiveCamera, Points, PointsMaterial, Quaternion, Scene, Vector3, WebGLRenderer } from 'three';
import { LineMaterial, OrbitControls, RGBELoader } from 'three/examples/jsm/Addons.js';
import { nextTick, onMounted, ref } from 'vue';


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

const engine = {
  renderer: null,
  scene: null,
  camera: null,
  orbit: null,
  envMap: null,
  object: null
}

const init = () => {
  nextTick(setupEnv);
}

onMounted(init);

const CORNERSEGMENTS = 20;
const LINESEGMENTS = 20;
const ROTATESEGMENTS = 40;

const generateBottleBody = (params, offset=0) => {
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
  let axis = axis_0.clone().cross(axis_1);
  

  let rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResA.round.angle/(CORNERSEGMENTS-1));
  let dir = axis_0.clone();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResA.round.o.clone().add(dir.clone().multiplyScalar(bottomCorner));
    points.push(target);
  }

  // points.length = 0;

  const O1_B_B = new LineCurve3(roundResA.oc, roundResB.oa);
  points.push(...O1_B_B.getPoints(LINESEGMENTS));

  axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  axis = axis_0.clone().cross(axis_1);
  

  rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResB.round.angle/(CORNERSEGMENTS-1));
  dir = axis_0.clone();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o.clone().add(dir.clone().multiplyScalar(topCorner));
    points.push(target);
  }

  const O2_C = new LineCurve3(roundResB.oc, C);

  points.push(...O2_C.getPoints(LINESEGMENTS));

  const D = new Vector3(neckRadius, height + neckHeight, 0)
  const CD = new LineCurve3(C, D);

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
    const normal = prev_current.add(current_next).normalize();
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



  const fin_points = totalPoints.flatMap(points => [...points]);
  const data = {
    indices,
    points: fin_points,
    row: f_points.length
  }
  // const geometry = new BufferGeometry().setFromPoints(fin_points);
  // geometry.setIndex(new BufferAttribute(new Uint16Array(indices), 1))
  // geometry.computeVertexNormals();

  // const geometry = new BufferGeometry().setFromPoints(f_points);
  // geometry.setIndex(new BufferAttribute(new Uint16Array(indices), 1))
  // geometry.computeVertexNormals();

  // const inenrPoints = fin_points.map(item => item.clone());
  // const normals = [];
  // const normalArray = geometry.attributes.normal.array;
  // for(let i=0; i<normalArray.length; i+=3) {
  //   normals.push(
  //     new Vector3(normalArray[i], normalArray[i+1], normalArray[i+2])
  //   );
  // }

  // inenrPoints.forEach((point, index) => {
  //   point.add(
  //     normals[index].clone().multiplyScalar(thickness)
  //   )
  // })

  // const fin_points_inner = inenrPoints
  // // .flatMap(points => [...points]);
  // console.log(fin_points_inner, 'fin_points_inner')
  // const finGeometry = new BufferGeometry().setFromPoints([...fin_points, ...fin_points_inner]);
  // // const finGeometry = new BufferGeometry().setFromPoints([...fin_points_inner]);
  // const originIndiceLen = indices.length;
  // const reverseIndices = [...indices].reverse()
  // console.log(indices.length);
  // for(let i=0; i<originIndiceLen; i++) {
  //   indices.push(reverseIndices[i] + fin_points.length);
  // }

  // const eachColumn = fin_points.length / (ROTATESEGMENTS - 1);
  // console.log(eachColumn, 'eachColumn', pointsArray.length)

  // for(let i=0; i<ROTATESEGMENTS-1; i++) {
  //   let leftBottom = i * eachColumn + eachColumn-1;
  //   let leftTop = leftBottom + fin_points.length;
  //   let rightBottom = leftBottom + eachColumn;
  //   if(i===ROTATESEGMENTS-2) {
  //     rightBottom = eachColumn-1;
  //   }
  //   let rightTop = rightBottom + fin_points.length;
  //   indices.push(leftTop, leftBottom, rightBottom, leftTop, rightBottom, rightTop);
  // }

  // console.log(indices.length)
  // finGeometry.setIndex(new BufferAttribute(new Uint16Array(indices), 1))
  // finGeometry.computeVertexNormals();



  // const mesh = new Mesh(
  //   geometry,
  //   new MeshPhysicalMaterial(
  //     {
  //       envMap: engine.envMap,
  //       side: DoubleSide,
  //       wireframe: true
  //     }
  //   )
  // );

  // const mesh = new Line(
  //   geometry,
  //   new LineBasicMaterial()
  // );

  return data;
}

const generateBottleCap = (params) => {
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
  let axis = axis_0.clone().cross(axis_1);
  

  let rotateQuat = new Quaternion().setFromAxisAngle(axis, roundResB.round.angle/(CORNERSEGMENTS-1));
  let dir = axis_0.clone();
  for(let i=0; i< CORNERSEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o.clone().add(dir.clone().multiplyScalar(neckCorner));
    points.push(target);
  }

  const O1_B_C = new LineCurve3(roundResB.oc, C);
  points.push(...O1_B_C.getPoints(LINESEGMENTS));

  const pointsArray = [...points];
  const f_points = [];
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
  const geometry = new BufferGeometry().setFromPoints(fin_points);
  geometry.setIndex(new BufferAttribute(new Uint16Array(indices), 1))
  geometry.computeVertexNormals();
  
  const mesh = new Mesh(
    geometry,
    new MeshPhysicalMaterial(
      {
        envMap: engine.envMap,
        side: DoubleSide,
        wireframe: true
      }
    )
  );

  return mesh;
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
  const oa_o = rotateAxis.cross(ab.clone().normalize()).multiplyScalar(radius);
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
        wireframe: true
      }
    )
  );

  return mesh;

}

const changeBottle = (neckRadius = 20, topRadius=40, bottomRadius=30, height=80, neckHeight=18, bottomCorner=2, topCorner=2, thickness=5) => {
  const bottleOuter = generateBottleBody({
    neckRadius,
    topRadius,
    bottomRadius,
    height,
    neckHeight,
    bottomCorner,
    topCorner,
    thickness
  }, 0);
  const bottleInner = generateBottleBody({
    neckRadius,
    topRadius,
    bottomRadius,
    height,
    neckHeight,
    bottomCorner,
    topCorner,
    thickness
  }, thickness);
  
  const points = [...bottleInner.points, ...bottleOuter.points];
  
  const outerIndex = [...bottleOuter.indices]
  outerIndex.forEach((value, index) => {
    outerIndex[index] += bottleInner.points.length;
  });
  const index = [...bottleInner.indices, ...outerIndex];

  for(let i=0; i<ROTATESEGMENTS-1; i++) {
    let leftTop = i * bottleInner.row + bottleInner.row-1;
    let leftBottom = i * bottleOuter.row + bottleOuter.row-1 + bottleInner.points.length;
    let rightTop = leftTop + bottleInner.row;
    let rightBottom = leftBottom + bottleOuter.row;
    if(i===ROTATESEGMENTS-2) {
      rightTop = bottleInner.row-1;
      rightBottom = bottleOuter.row-1 + bottleInner.points.length
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

  const geometry = new BufferGeometry().setFromPoints(points);
  geometry.setIndex(new BufferAttribute(new Uint16Array(index), 1))
  geometry.computeVertexNormals();
  const mesh = new Mesh(
    geometry,
    new MeshPhysicalMaterial(
      {
        envMap: engine.envMap,
        side: DoubleSide,
        wireframe: true
      }
    )
  );

  const capParams = {
    radius: neckRadius + 2,
    neckCorner: 5,
    height: 15
  }
  const cap = generateBottleCap(capParams);
  const group = new Group();
  cap.position.y = height + neckHeight - capParams.height + capParams.neckCorner;
  // bottleInner.position.y = bottleThickness;
  // group.add(cap);
  group.add(mesh);
  // group.add(bottleOuter);
  if(engine.object) {
    engine.scene.remove(engine.object)
  }
  engine.scene.add(group);
  engine.object = group;
}

console.log(changeBottle)

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
  engine.camera = new PerspectiveCamera();
  engine.camera.near = 0.01;
  engine.camera.far = 5000;
  engine.orbit = new OrbitControls(engine.camera, engine.renderer.domElement);
  container.value.appendChild(engine.renderer.domElement);

  const envMap = await new RGBELoader().loadAsync("/public/7c4487d5-9e85-4b55-901c-d1a7a97a7e08.hdr");
  envMap.mapping = EquirectangularReflectionMapping;
  engine.envMap = envMap;


  const grid = new GridHelper(400, 20);
  engine.scene.add(grid);

  engine.camera.position.set(10, 10, 10);
  engine.camera.lookAt(0, 0, 0);
  onResize();
  render();

  setObjects();
}

const setObjects = () => {
  changeBottle()
  console.log(changeBottle)
}

const render = () => {
  engine.orbit.update();
  engine.renderer.render(engine.scene, engine.camera);
  requestAnimationFrame(render);
}


</script>

<template>
  <div ref="container" id="container">
    
  </div>
</template>

<style scoped>

#container{
  width: 100%;
  height: 100%;
}

</style>
