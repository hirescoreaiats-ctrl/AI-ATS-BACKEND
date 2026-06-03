import { useMemo } from "react";

export function useVirtualRows(rows, rowHeight = 56, viewportHeight = 520, scrollTop = 0, overscan = 6) {
  return useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const visibleCount = Math.ceil(viewportHeight / rowHeight) + overscan * 2;
    const end = Math.min(rows.length, start + visibleCount);
    return {
      rows: rows.slice(start, end),
      offsetTop: start * rowHeight,
      totalHeight: rows.length * rowHeight
    };
  }, [rows, rowHeight, viewportHeight, scrollTop, overscan]);
}
