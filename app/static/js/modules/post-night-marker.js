// Post-Night Marker Module
// Colors the day after a night shift a lighter purple to indicate
// it's a recovery day, not a true day off.

import { classifyCell } from "./shift-classifier.js";

export class PostNightMarker {
  constructor() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () =>
        this.markPostNightCells(),
      );
    } else {
      setTimeout(() => this.markPostNightCells(), 50);
    }
  }

  markPostNightCells() {
    const tables = document.querySelectorAll("table");
    tables.forEach((table) => this.processTable(table));
  }

  processTable(table) {
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    if (rows.length === 0) return;

    const allDayCells = [];
    rows.forEach((row) => {
      const cells = Array.from(row.querySelectorAll('td[id="cell"]'));
      allDayCells.push(...cells);
    });

    for (let i = 0; i < allDayCells.length - 1; i++) {
      const cell = allDayCells[i];
      const nextCell = allDayCells[i + 1];

      if (this.isNightShift(cell) && this.isDayOff(nextCell)) {
        nextCell.classList.remove("day_off");
        nextCell.classList.add("post-night-recovery");

        // Add sleeping icon
        const timeEl = nextCell.querySelector(".time-text");
        if (timeEl) {
          // timeEl.innerHTML += '<div style="font-size:medium;">🛏️</div>';
          timeEl.innerHTML +=
            '<div><img src="/static/img/bed.png" alt="recovery" style="width:10px;height:10px;opacity:0.4;margin-left:-50px;"></div>';
        }
      }
    }
  }

  isNightShift(td) {
    if (td.classList.contains("evening")) return true;
    const timeText = td.querySelector(".time-text")?.textContent || "";
    const customText = td.querySelector(".custom-text")?.textContent || "";
    return classifyCell(timeText, customText) === "evening";
  }

  isDayOff(td) {
    if (td.classList.contains("day_off")) return true;
    const timeText = td.querySelector(".time-text")?.textContent || "";
    const customText = td.querySelector(".custom-text")?.textContent || "";
    return classifyCell(timeText, customText) === "day_off";
  }
}
