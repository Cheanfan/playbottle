import { LineCurve3, Quaternion, Vector3 } from "three";
import { removeRepeatPoints, removeSelfIntersections } from "../utils";

class ArcLine {
  a = new Vector3();
  b = new Vector3();
  c = new Vector3();
  o = new Vector3();
  oa = new Vector3();
  oc = new Vector3();
  radius = 1;
  angle = 0;
  isArcLine = true;
  arcSegments = 30;
  lineSegments = 30;
  spacedPoints = [];

  constructor(a, b, c, radius, arcSegments = 30, lineSegments = 30) {
    this.a.copy(a);
    this.b.copy(b);
    this.c.copy(c);
    this.radius = radius;
    const { oa, oc, round } = ArcLine.makeArcByPoints(a, b, c, this.radius);
    this.oa.copy(oa);
    this.oc.copy(oc);
    this.o.copy(round.o);
    this.angle = round.angle;
    this.arcSegments = arcSegments;
    this.lineSegments = lineSegments;
    this._makeSpacedPoints();
  }

  _makeSpacedPoints() {
    this.spacedPoints.length = 0;
    const points = [];
    const a_oa = new LineCurve3(this.a, this.oa);
    points.push(...a_oa.getSpacedPoints(this.lineSegments - 1));

    let axis_o_oa = this.oa.clone().sub(this.o).normalize();
    let axis_o_oc = this.oc.clone().sub(this.o).normalize();
    let axis = axis_o_oa.clone().cross(axis_o_oc).normalize();
    let rotateQuat = new Quaternion().setFromAxisAngle(
      axis,
      this.angle / (this.arcSegments - 1)
    );
    let dir = axis_o_oa.clone();
    for (let i = 0; i < this.arcSegments - 1; i++) {
      dir.applyQuaternion(rotateQuat).normalize();
      const target = this.o
        .clone()
        .add(dir.clone().multiplyScalar(this.radius));
      points.push(target);
    }
    this.spacedPoints.push(...points);
  }

  static makeArcByPoints(a, b, c, radius) {
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
    const rotateAxis = ab
      .clone()
      .normalize()
      .cross(bc.clone().normalize())
      .normalize();
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
  }
}

class SimpleArcLineList {
  name = "";
  list = [];
  spacedPoints = [];
  segments = 30;
  constructor(list) {
    this.list.length = 0;
    this.list.push(...list);
    this._makeSpacedPoints();
  }

  _makeSpacedPoints() {
    let prevPoint = null;
    this.spacedPoints.length = 0;
    for (let i = 0; i < this.list.length; i++) {
      const current = this.list[i];
      if (current.isArcLine) {
        this.spacedPoints.push(...current.spacedPoints);
        prevPoint = this.spacedPoints[this.spacedPoints.length - 1];
      } else {
        if (prevPoint) {
          this.spacedPoints.push(
            ...new LineCurve3(prevPoint, current).getSpacedPoints(this.segments)
          );
          prevPoint = this.spacedPoints[this.spacedPoints.length - 1];
        }
        prevPoint = current;
      }
    }
    const removedPoints = removeRepeatPoints(this.spacedPoints);
    this.spacedPoints.length = 0;
    this.spacedPoints.push(...removedPoints);
  }
}

export { SimpleArcLineList, ArcLine };
