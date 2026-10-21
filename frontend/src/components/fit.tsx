'use client';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

/** True on narrow screens, where the page flows and scrolls normally instead of fitting the viewport. */
function useFlowLayout() {
  const [flow, setFlow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 960px)');
    const update = () => setFlow(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return flow;
}

/**
 * Counts how many fixed-size items fit in the element behind `ref`.
 * `itemSize` includes the gap between items; `head` is space used by a sticky header.
 */
export function useFitCount(itemSize: number, { head = 0, gap = 0, fallback = 6 } = {}) {
  const ref = useRef<HTMLDivElement>(null);
  const flow = useFlowLayout();
  const [count, setCount] = useState(fallback);
  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const height = el.clientHeight - head;
    setCount(Math.max(1, Math.floor((height + gap) / itemSize)));
  }, [itemSize, head, gap]);
  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el || flow) return;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [measure, flow]);
  return { ref, count: flow ? fallback : count, flow };
}

export function usePager<T>(items: T[], size: number) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(page, pages - 1);
  useEffect(() => {
    if (page !== current) setPage(current);
  }, [page, current]);
  return {
    page: current,
    pages,
    setPage,
    rows: items.slice(current * size, current * size + size),
    from: items.length ? current * size + 1 : 0,
    to: Math.min(items.length, current * size + size),
    total: items.length,
  };
}

export function Pager({
  page,
  pages,
  onChange,
  from,
  to,
  total,
  compact = false,
}: {
  page: number;
  pages: number;
  onChange: (page: number) => void;
  from?: number;
  to?: number;
  total?: number;
  compact?: boolean;
}) {
  return (
    <nav className={'pager' + (compact ? ' pager-compact' : '')} aria-label="Paginação" data-idle={pages <= 1}>
      {!compact && total !== undefined && (
        <span className="pager-info">
          {from}–{to} de {total}
        </span>
      )}
      <div className="pager-controls">
        <button className="icon-btn" aria-label="Página anterior" disabled={page <= 0} onClick={() => onChange(page - 1)}>
          <ChevronLeft size={16} />
        </button>
        <span className="pager-page">
          {page + 1} / {pages}
        </span>
        <button
          className="icon-btn"
          aria-label="Próxima página"
          disabled={page >= pages - 1}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </nav>
  );
}

/** A vertical list of fixed-height items that paginates instead of scrolling. */
export function FitList<T>({
  items,
  itemSize,
  gap = 10,
  render,
  empty,
  fallback = 4,
}: {
  items: T[];
  itemSize: number;
  gap?: number;
  render: (item: T) => ReactNode;
  empty?: ReactNode;
  fallback?: number;
}) {
  const { ref, count } = useFitCount(itemSize + gap, { gap, fallback });
  const pager = usePager(items, count);
  return (
    <div className="fit-column">
      <div ref={ref} className="fit-list" style={{ gap }}>
        {pager.rows.map(render)}
        {!items.length && empty}
      </div>
      <Pager compact page={pager.page} pages={pager.pages} onChange={pager.setPage} />
    </div>
  );
}

export const TABLE_ROW = 52;
export const TABLE_HEAD = 40;

/** Table area that shows as many rows as fit the available height, with a pager below. */
export function PagedTable<T>({
  rows,
  header,
  renderRow,
  rowHeight = TABLE_ROW,
  fallback = 8,
  className = '',
}: {
  rows: T[];
  header: ReactNode;
  renderRow: (row: T) => ReactNode;
  rowHeight?: number;
  fallback?: number;
  className?: string;
}) {
  const { ref, count } = useFitCount(rowHeight, { head: TABLE_HEAD, fallback });
  const pager = usePager(rows, count);
  return (
    <>
      <div ref={ref} className={'fit-area ' + className}>
        <table className="data-table fit-table" style={{ ['--row' as string]: rowHeight + 'px' }}>
          <thead>{header}</thead>
          <tbody>{pager.rows.map(renderRow)}</tbody>
        </table>
      </div>
      <Pager {...pager} onChange={pager.setPage} />
    </>
  );
}

/** A responsive grid of fixed-height cards that paginates instead of scrolling. */
export function FitGrid<T>({
  items,
  itemHeight,
  minWidth = 300,
  gap = 16,
  render,
  fallback = 6,
}: {
  items: T[];
  itemHeight: number;
  minWidth?: number;
  gap?: number;
  render: (item: T) => ReactNode;
  fallback?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const flow = useFlowLayout();
  const [size, setSize] = useState({ cols: 3, rows: Math.ceil(fallback / 3) });
  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el || flow) return;
    const measure = () => {
      const cols = Math.max(1, Math.floor((el.clientWidth + gap) / (minWidth + gap)));
      const rows = Math.max(1, Math.floor((el.clientHeight + gap) / (itemHeight + gap)));
      setSize({ cols, rows });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [flow, gap, itemHeight, minWidth]);
  const count = flow ? fallback : size.cols * size.rows;
  const pager = usePager(items, count);
  return (
    <>
      <div ref={ref} className="fit-area">
        <div
          className="fit-grid"
          style={{
            gridTemplateColumns: `repeat(${flow ? 1 : size.cols}, minmax(0, 1fr))`,
            gridAutoRows: itemHeight,
            gap,
          }}
        >
          {pager.rows.map(render)}
        </div>
      </div>
      <Pager {...pager} onChange={pager.setPage} />
    </>
  );
}

export function useElementHeight() {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setHeight(el.clientHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return { ref, height };
}
