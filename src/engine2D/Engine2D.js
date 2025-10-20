import { Vector3 } from "three";
import Two from "two.js";
import { CenterLine, SegmentLineShape } from "./shapes/simpleShape";

class Engine2D {
  two = null;
  shapeLists = [];
  part2ds = [];
  contaienr = null;
  constructor(container) {
    this.contaienr = container;
  }

  _makeShapeByPoints(points, width, height) {
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    // svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);

    const segments = new SegmentLineShape(points);
    const segmentPath = segments.makePath();

    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    points.forEach((p) => {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    });
    let start = [minX * 0.5 + maxX * 0.5, minY];
    let end = [minX * 0.5 + maxX * 0.5, maxY];
    let yPadding = (maxY - minY) * 0.1;
    yPadding = Math.max(yPadding, 6);
    start[1] -= yPadding * 0.5;
    end[1] += yPadding * 0.5;

    const centerLine = new CenterLine(start, end);
    const centerLinePath = centerLine.makePath();
    const shapes = [segments, centerLine];
    svg.appendChild(segmentPath);
    svg.appendChild(centerLinePath);
    return { svg, shapes };
  }

  addShapeList(shapeList) {
    this.shapeLists.push(shapeList);
    // this._updateDraw();
  }

  _computeShapeListBound(points) {
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    points.forEach((item) => {
      if (item.x > maxX) {
        maxX = item.x;
      }
      if (item.x < minX) {
        minX = item.x;
      }
      if (item.y > maxY) {
        maxY = item.y;
      }
      if (item.y < minY) {
        minY = item.y;
      }
    });
    return {
      minX,
      maxX,
      minY,
      maxY,
    };
  }

  _makeShapeByList(pointLists) {
    const bound = this._computeShapeListBound(pointLists[0]);
    const { minX, maxX, minY, maxY } = bound;
    const xRange = maxX - minX;
    const yRange = maxY - minY;
    let padding = Math.max(xRange, yRange) * 0.1;
    padding = Math.max(padding, 10);
    const centerX = (minX + maxX) * 0.5;
    const centerY = (minY + maxY) * 0.5;
    const transformedOutPoints = [];
    const transformedInnerPoints = [];
    for (let i = 0; i < pointLists[0].length; i++) {
      const p = pointLists[0][i].clone();
      p.sub(new Vector3(centerX, centerY, 0));
      p.y *= -1;
      p.x += centerX + xRange * 0.5 + padding;
      p.y += centerY + padding;
      transformedOutPoints.push(p);
    }
    if (pointLists[1]) {
      for (let i = 0; i < pointLists[1].length; i++) {
        const p = pointLists[1][i].clone();
        p.sub(new Vector3(centerX, centerY, 0));
        p.y *= -1;
        p.x += centerX + xRange * 0.5 + padding;
        p.y += centerY + padding;
        transformedInnerPoints.push(p);
      }
    }
    transformedInnerPoints.reverse();
    const allPoints = [...transformedOutPoints];
    if (pointLists[1]) {
      allPoints.push(...transformedInnerPoints);
      allPoints.push(transformedOutPoints[0]);
    }

    const { svg, shapes } = this._makeShapeByPoints(
      allPoints,
      xRange + padding * 2,
      yRange + padding * 2
    );
    svg.style.position = "absolute";
    return { svg, shapes };
  }

  updateDraw() {
    const bounds = [];
    // compute bounding
    let left = 0;
    for (let i = 0; i < this.shapeLists.length; i++) {
      // const shapeList = this.shapeList[i];
      // const bound = this._computeShapeListBound(shapeList);
      // bounds.push(bound);
      const { svg, shapes } = this._makeShapeByList(this.shapeLists[i].points);
      this.part2ds.push({
        name: this.shapeLists[i].name,
        shapes: shapes,
      });
      svg.style.left = `${left}`;
      svg.style.top = `0`;
      left += Number(svg.getAttribute("width"));
      console.log(left);
      this.contaienr.appendChild(svg);
    }
    console.log(this);
  }

  onUpdate() {}
}

export { Engine2D };
