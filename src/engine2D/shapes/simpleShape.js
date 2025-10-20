class BaseShape {
  type = "baseShape";
  path = null;
}

class SegmentLineShape extends BaseShape {
  points = [];
  type = "segmentLine";
  constructor(points) {
    super();
    this.points.length = 0;
    this.points.push(...points);
  }
  makePath() {
    const svgNS = "http://www.w3.org/2000/svg";
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#000000");
    path.setAttribute("stroke-width", 1);
    const points = this.points;
    let pathData = "M" + points[0].x + "," + points[0].y; // 移动到第一个点
    for (let i = 1; i < points.length; i++) {
      pathData += " L" + points[i].x + "," + points[i].y; // 画线到下一个点
    }

    // 设置路径数据
    path.setAttribute("d", pathData);
    this.path = path;
    return path;
  }
}

class CenterLine extends BaseShape {
  start = [0, 0];
  end = [0, 0];
  constructor(start, end) {
    super();
    this.start.length = 0;
    this.end.length = 0;
    this.start.push(...start);
    this.end.push(...end);
  }
  makePath() {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", this.start[0]);
    line.setAttribute("y1", this.start[1]);
    line.setAttribute("x2", this.end[0]);
    line.setAttribute("y2", this.end[1]);
    line.setAttribute("stroke", "#000000");
    line.setAttribute("stroke-width", 1);
    line.setAttribute("stroke-dasharray", "5, 5");
    line.setAttribute("opacity", 1);
    this.path = line;
    return line;
  }
}

export { SegmentLineShape, CenterLine };
