import { BufferAttribute, BufferGeometry } from "three";
import { Quaternion, Vector3, LineCurve3 } from "three";

const ROTATESEGMENTS = 30;

export const removeRepeatPoints = (points) => {
  let prev = null;
  let newPoints = [];
  points.forEach((point) => {
    if (prev) {
      const dist = point.distanceTo(prev);
      if (dist > 1e-5) {
        newPoints.push(point);
      }
    } else {
      newPoints.push(point);
    }
    prev = point;
  });
  return newPoints;
};

export const removeSelfIntersections = (points) => {
  const EPS = 1e-9;
  // 复制一份，避免改动原数组
  const pts = points.map((p) => p.clone());

  if (pts.length < 4) return pts; // 少于两段不可能自交

  // 线段严格内点相交（排除端点相交），返回交点与参数 t,u
  function intersect2D(A, B, C, D) {
    const ax = A.x,
      ay = A.y,
      bx = B.x,
      by = B.y;
    const cx = C.x,
      cy = C.y,
      dx = D.x,
      dy = D.y;

    const r_x = bx - ax,
      r_y = by - ay;
    const s_x = dx - cx,
      s_y = dy - cy;

    const denom = r_x * s_y - r_y * s_x;
    if (Math.abs(denom) < EPS) return null; // 平行或共线，忽略

    const t = ((cx - ax) * s_y - (cy - ay) * s_x) / denom;
    const u = ((cx - ax) * r_y - (cy - ay) * r_x) / denom;

    // 严格在两条线段内部（避免端点/相邻段误判）
    if (t > EPS && t < 1 - EPS && u > EPS && u < 1 - EPS) {
      return {
        x: ax + t * r_x,
        y: ay + t * r_y,
        t,
        u,
      };
    }
    return null;
  }

  // 去重相邻重复点（可能因数值误差产生）
  function squashConsecutiveDuplicates(arr) {
    const out = [];
    for (let k = 0; k < arr.length; k++) {
      if (k === 0) {
        out.push(arr[k]);
        continue;
      }
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
    outer: for (let i = 0; i < pts.length - 1; i++) {
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
          pts.length = 0;
          pts.push(...cleaned);

          changed = true;
          break outer; // 结构改变后从头重新搜索
        }
      }
    }
  }

  return pts;
};

export const rotateColumnPoints = (points, angle, segments) => {
  const totalPoints = [];
  const rotate_step = angle / (segments - 1);
  const rotateQuat = new Quaternion().setFromAxisAngle(
    new Vector3(0, 1, 0),
    rotate_step
  );

  let rotated_points = null;
  const indices = [];
  for (let i = 0; i < segments - 1; i++) {
    if (rotated_points) {
      let origin_points = rotated_points;
      rotated_points = rotated_points.map((point) => {
        return point.clone().applyQuaternion(rotateQuat);
      });
      for (let j = 1; j < origin_points.length; j++) {
        const leftTop = (i - 1) * origin_points.length + j - 1;
        const leftBottom = (i - 1) * origin_points.length + j;
        const rightTop = i * origin_points.length + j - 1;
        const rightBottom = i * origin_points.length + j;
        indices.push(
          leftTop,
          leftBottom,
          rightBottom,
          leftTop,
          rightBottom,
          rightTop
        );
      }
      if (i == segments - 2) {
        for (let j = 1; j < origin_points.length; j++) {
          const leftTop = i * origin_points.length + j - 1;
          const leftBottom = i * origin_points.length + j;
          const rightTop = j - 1;
          const rightBottom = j;
          indices.push(
            leftTop,
            leftBottom,
            rightBottom,
            leftTop,
            rightBottom,
            rightTop
          );
        }
      }
    } else {
      rotated_points = points;
    }
    totalPoints.push(rotated_points);
  }
  const fin_points = totalPoints.flatMap((points) => [...points]);
  const data = {
    indices,
    points: fin_points,
    points2d: points,
  };
  return data;
};

const roundCorner = (a, b, c, radius) => {
  const ab = b.clone().sub(a);
  const bc = c.clone().sub(b);
  const cosAlpha = ab
    .clone()
    .normalize()
    .dot(bc.clone().normalize().multiplyScalar(-1));
  let alpha = Math.acos(cosAlpha);
  const halfAlpha = alpha * 0.5;
  const oa = b.clone().sub(
    ab
      .clone()
      .normalize()
      .multiplyScalar(radius / Math.tan(halfAlpha))
  );
  const oc = b.clone().add(
    bc
      .clone()
      .normalize()
      .multiplyScalar(radius / Math.tan(halfAlpha))
  );
  const rotateAxis = ab.clone().normalize().cross(bc.clone().normalize());
  const oa_o = rotateAxis
    .cross(ab.clone().normalize())
    .normalize()
    .multiplyScalar(radius);
  const o = oa_o.add(oa);
  const round = {
    o,
    angle: Math.PI - alpha,
  };
  return {
    oa,
    oc,
    round,
  };
};

export const makeCurvePointsOffset = (points, offset) => {
  const z = new Vector3(0, 0, -1);
  let pointsTemp = [];
  for (let i = 0; i < points.length; i++) {
    let prev = points[i - 1];
    const current = points[i];
    let next = points[i + 1];
    if (!prev) {
      prev = current.clone().add(current.clone().sub(next));
    }
    if (!next) {
      next = current.clone().add(current.clone().sub(prev));
    }
    const prev_current = current.clone().sub(prev).normalize();
    prev_current.cross(z).normalize();
    const current_next = next.clone().sub(current).normalize();
    current_next.cross(z).normalize();
    const normal = current_next;
    pointsTemp.push(current.clone().add(normal.multiplyScalar(offset)));
  }

  if (Math.abs(offset) > 0.01) {
    pointsTemp = removeSelfIntersections(pointsTemp);
  }
  return pointsTemp;
};

export const createThread = (params) => {
  const THREAD_SEGMENTS = 10;
  const { crestWidth, pitch, rounds, radius, angle, crestHeight } = params;
  let angle_rad = (angle / 180) * Math.PI;
  // 牙宽 45°
  const A = new Vector3();
  const B = new Vector3(crestHeight, crestHeight / Math.tan(angle_rad), 0);
  const C = new Vector3(
    crestHeight,
    crestWidth - crestHeight / Math.tan(angle_rad),
    0
  );
  const D = new Vector3(0, crestWidth, 0);
  const corner = 0.15;
  const roundResB = roundCorner(A, B, C, corner);
  const O1_B = roundResB.oc;
  const roundResC = roundCorner(O1_B, C, D, corner);
  const points = [];
  const A_O1_A = new LineCurve3(A, roundResB.oa);
  points.push(...A_O1_A.getPoints(THREAD_SEGMENTS));

  const originCenter = A.clone().add(D).multiplyScalar(0.5);

  let axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  let axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  let axis = axis_0.clone().cross(axis_1).normalize();

  let rotateQuat = new Quaternion().setFromAxisAngle(
    axis,
    roundResB.round.angle / (THREAD_SEGMENTS - 1)
  );
  let dir = axis_0.clone();
  points.pop();
  for (let i = 0; i < THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o
      .clone()
      .add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

  const O1_B_O2_C = new LineCurve3(roundResB.oc, roundResC.oa);
  points.pop();
  points.push(...O1_B_O2_C.getPoints(THREAD_SEGMENTS));

  axis_0 = roundResC.oa.clone().sub(roundResC.round.o).normalize();
  axis_1 = roundResC.oc.clone().sub(roundResC.round.o).normalize();
  axis = axis_0.clone().cross(axis_1);

  rotateQuat = new Quaternion().setFromAxisAngle(
    axis,
    roundResC.round.angle / (THREAD_SEGMENTS - 1)
  );
  dir = axis_0.clone();
  points.pop();
  for (let i = 0; i < THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResC.round.o
      .clone()
      .add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

  const O2_C_D = new LineCurve3(roundResC.oc, D);
  points.pop();
  points.push(...O2_C_D.getPoints(THREAD_SEGMENTS));

  points.forEach((point) => {
    point.x += radius;
  });

  originCenter.x += radius;

  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach((point) => {
    if (prev) {
      const dist = point.distanceTo(prev);
      if (dist > 1e-6) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });

  const totalPoints = [];

  let totalSteps = ROTATESEGMENTS * rounds;
  totalSteps = Math.ceil(totalSteps);
  const rotate_step = (Math.PI * 2 * rounds) / (totalSteps - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(
    new Vector3(0, 1, 0),
    rotate_step
  );
  let rotated_points = null;
  const indices = [];
  let originCenterCopy = originCenter.clone();
  for (let i = 0; i < totalSteps; i++) {
    if (rotated_points) {
      originCenterCopy.applyQuaternion(rotateQuat);
      let origin_points = rotated_points;
      rotated_points = rotated_points.map((point) => {
        return point.clone().applyQuaternion(rotateQuat);
      });
      for (let j = 1; j < origin_points.length; j++) {
        const leftTop = (i - 1) * origin_points.length + j - 1;
        const leftBottom = (i - 1) * origin_points.length + j;
        const rightTop = i * origin_points.length + j - 1;
        const rightBottom = i * origin_points.length + j;
        indices.push(
          leftTop,
          leftBottom,
          rightBottom,
          leftTop,
          rightBottom,
          rightTop
        );
      }
    } else {
      rotated_points = f_points;
    }
    totalPoints.push(rotated_points);
  }

  totalPoints.forEach((points, idx) => {
    points.forEach((point) => {
      point.y += (idx * rounds * pitch) / totalSteps;
    });
  });

  originCenterCopy.y += rounds * pitch;
  totalPoints.push([originCenter, originCenterCopy]);

  const fin_points = totalPoints.flatMap((points) => [...points]);

  const originIndex = fin_points.length - 2;
  const originCopyIndex = fin_points.length - 1;

  for (let j = 1; j < rotated_points.length; j++) {
    const o1 = originIndex;
    const a1 = j - 1;
    const b1 = j;
    indices.push(o1, b1, a1);

    const o2 = originCopyIndex;
    const a2 = a1 + rotated_points.length * (totalSteps - 1);
    const b2 = b1 + rotated_points.length * (totalSteps - 1);
    indices.push(o2, b2, a2);
  }

  const data = {
    indices,
    points: fin_points,
    row: f_points.length,
  };

  return data;
};

export const createInnerThread = (params) => {
  const THREAD_SEGMENTS = 10;
  const { crestWidth, pitch, rounds, radius, angle, crestHeight } = params;
  let angle_rad = (angle / 180) * Math.PI;
  // 牙宽 45°
  const A = new Vector3();
  const B = new Vector3(-crestHeight, crestHeight / Math.tan(angle_rad), 0);
  const C = new Vector3(
    -crestHeight,
    crestWidth - crestHeight / Math.tan(angle_rad),
    0
  );
  const D = new Vector3(0, crestWidth, 0);
  const corner = 0.15;
  const roundResB = roundCorner(A, B, C, corner);
  console.log((roundResB.round.angle * 180) / Math.PI);
  const O1_B = roundResB.oc;
  const roundResC = roundCorner(O1_B, C, D, corner);
  const points = [];
  const A_O1_A = new LineCurve3(A, roundResB.oa);
  points.push(...A_O1_A.getPoints(THREAD_SEGMENTS));

  const originCenter = A.clone().add(D).multiplyScalar(0.5);

  let axis_0 = roundResB.oa.clone().sub(roundResB.round.o).normalize();
  let axis_1 = roundResB.oc.clone().sub(roundResB.round.o).normalize();
  let axis = axis_0.clone().cross(axis_1).normalize();

  let rotateQuat = new Quaternion().setFromAxisAngle(
    axis,
    roundResB.round.angle / (THREAD_SEGMENTS - 1)
  );
  let dir = axis_0.clone();
  points.pop();
  for (let i = 0; i < THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResB.round.o
      .clone()
      .add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

  const O1_B_O2_C = new LineCurve3(roundResB.oc, roundResC.oa);
  points.pop();
  points.push(...O1_B_O2_C.getPoints(THREAD_SEGMENTS));

  axis_0 = roundResC.oa.clone().sub(roundResC.round.o).normalize();
  axis_1 = roundResC.oc.clone().sub(roundResC.round.o).normalize();
  axis = axis_0.clone().cross(axis_1);

  rotateQuat = new Quaternion().setFromAxisAngle(
    axis,
    roundResC.round.angle / (THREAD_SEGMENTS - 1)
  );
  dir = axis_0.clone();
  points.pop();
  for (let i = 0; i < THREAD_SEGMENTS; i++) {
    dir.applyQuaternion(rotateQuat).normalize();
    const target = roundResC.round.o
      .clone()
      .add(dir.clone().multiplyScalar(corner));
    points.push(target);
  }

  const O2_C_D = new LineCurve3(roundResC.oc, D);
  points.pop();
  points.push(...O2_C_D.getPoints(THREAD_SEGMENTS));

  points.forEach((point) => {
    point.x += radius + crestHeight;
  });

  originCenter.x += radius + crestHeight;

  const pointsArray = [...points];
  let f_points = [];
  let prev = null;
  pointsArray.forEach((point) => {
    if (prev) {
      const dist = point.distanceTo(prev);
      if (dist > 1e-6) {
        f_points.push(point);
      }
    } else {
      f_points.push(point);
    }
    prev = point;
  });

  const totalPoints = [];

  let totalSteps = ROTATESEGMENTS * rounds;
  totalSteps = Math.ceil(totalSteps);
  const rotate_step = (Math.PI * 2 * rounds) / (totalSteps - 1);
  rotateQuat = new Quaternion().setFromAxisAngle(
    new Vector3(0, 1, 0),
    rotate_step
  );
  let rotated_points = null;
  const indices = [];
  let originCenterCopy = originCenter.clone();
  for (let i = 0; i < totalSteps; i++) {
    if (rotated_points) {
      originCenterCopy.applyQuaternion(rotateQuat);
      let origin_points = rotated_points;
      rotated_points = rotated_points.map((point) => {
        return point.clone().applyQuaternion(rotateQuat);
      });
      for (let j = 1; j < origin_points.length; j++) {
        const leftTop = (i - 1) * origin_points.length + j - 1;
        const leftBottom = (i - 1) * origin_points.length + j;
        const rightTop = i * origin_points.length + j - 1;
        const rightBottom = i * origin_points.length + j;
        indices.push(
          leftTop,
          leftBottom,
          rightBottom,
          leftTop,
          rightBottom,
          rightTop
        );
      }
    } else {
      rotated_points = f_points;
    }
    totalPoints.push(rotated_points);
  }

  totalPoints.forEach((points, idx) => {
    points.forEach((point) => {
      point.y += (idx * rounds * pitch) / totalSteps;
    });
  });

  originCenterCopy.y += rounds * pitch;
  totalPoints.push([originCenter, originCenterCopy]);

  const fin_points = totalPoints.flatMap((points) => [...points]);

  const originIndex = fin_points.length - 2;
  const originCopyIndex = fin_points.length - 1;

  for (let j = 1; j < rotated_points.length; j++) {
    const o1 = originIndex;
    const a1 = j - 1;
    const b1 = j;
    indices.push(o1, b1, a1);

    const o2 = originCopyIndex;
    const a2 = a1 + rotated_points.length * (totalSteps - 1);
    const b2 = b1 + rotated_points.length * (totalSteps - 1);
    indices.push(o2, b2, a2);
  }

  const data = {
    indices,
    points: fin_points,
    row: f_points.length,
  };

  return data;
};

export const mergeGeometries = (geometries) => {
  const indices = [];
  const positions = [];
  const uvs = [];
  const normals = [];
  for (let i = 0; i < geometries.length; i++) {
    const geometry = geometries[i];
    const positionArray = geometry.getAttribute("position").array;
    const uvArray = geometry.getAttribute("uv").array;
    const normalArray = geometry.getAttribute("normal").array;
    const indexArray = geometry.getIndex().array;
    positions.push(...positionArray);
    uvs.push(...uvArray);
    normals.push(...normalArray);
    indices.push(...indexArray);
  }
  const mergedGeometry = new BufferGeometry();
  const positionAttribute = new BufferAttribute(new Float32Array(positions), 3);
  const normalAttribute = new BufferAttribute(new Float32Array(normals), 3);
  const uvAttribute = new BufferAttribute(new Float32Array(uvs), 2);
  mergedGeometry.setIndex(new BufferAttribute(new Uint16Array(indices), 1));
  return mergedGeometry;
};
