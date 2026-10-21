'use client';
import type { DragEvent, ElementType, ReactNode } from 'react';
import { Plus } from 'lucide-react';

const cx = (...names: (string | false | undefined | null)[]) => names.filter(Boolean).join(' ');

/** Surface container. `fill` makes it take the remaining height of a fitting page and clip its content. */
export function Card({
  as: Tag = 'div',
  fill = false,
  className,
  children,
}: {
  as?: ElementType;
  fill?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return <Tag className={cx('card', fill && 'card-fill fill', className)}>{children}</Tag>;
}

export function CardHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="card-head">
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function CardBody({
  stack = false,
  className,
  children,
}: {
  stack?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return <div className={cx('card-body', stack && 'stack', className)}>{children}</div>;
}

export type TabItem<T extends string = string> = { value: T; label: ReactNode; icon?: ReactNode };

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  variant = 'pill',
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  label?: string;
  /** `pill` is the compact segmented control; `line` is the page-level underline tab bar. */
  variant?: 'pill' | 'line';
}) {
  return (
    <div className={cx('tabs', variant === 'line' && 'tabs-line')} role="tablist" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          className={cx('tab', value === item.value && 'active')}
          onClick={() => onChange(item.value)}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** Horizontal bar for tabs, search, filters and actions. Wrap trailing items in ToolbarEnd. */
export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="board-bar">{children}</div>;
}

export function ToolbarEnd({ children }: { children: ReactNode }) {
  return <div className="toolbar-end">{children}</div>;
}

/** The board scrolls horizontally; each column scrolls its own cards vertically. */
export function KanbanBoard({ natural = false, children }: { natural?: boolean; children: ReactNode }) {
  return <div className={cx('board', natural && 'board-natural')}>{children}</div>;
}

export function KanbanColumn<T>({
  title,
  dot,
  count,
  meta,
  items,
  render,
  empty,
  onAdd,
  addLabel,
  onDropId,
  label,
}: {
  title: string;
  dot?: string;
  count: number;
  meta?: ReactNode;
  items: T[];
  render: (item: T) => ReactNode;
  empty: string;
  /** Shows a "+" in the column header, e.g. to create an item already placed in this column. */
  onAdd?: () => void;
  addLabel?: string;
  /** Receives the dragged card id; omit to make the column read-only. */
  onDropId?: (id: string) => void;
  label?: string;
}) {
  return (
    <section
      className="kanban-column"
      aria-label={label}
      onDragOver={onDropId ? (e: DragEvent) => e.preventDefault() : undefined}
      onDrop={
        onDropId
          ? (e: DragEvent) => {
              e.preventDefault();
              const id = e.dataTransfer.getData('text/plain');
              if (id) onDropId(id);
            }
          : undefined
      }
    >
      <header className="kanban-column-header">
        {dot && <span className="kanban-dot" style={{ background: dot }} />}
        <strong className="kanban-column-title" title={title}>
          {title}
        </strong>
        <span className="tab-count">{count}</span>
        {onAdd && (
          <button type="button" className="icon-btn kanban-add" aria-label={addLabel || 'Adicionar em ' + title} title={addLabel || 'Adicionar'} onClick={onAdd}>
            <Plus size={16} />
          </button>
        )}
      </header>
      {meta && <div className="kanban-column-meta">{meta}</div>}
      <div className="kanban-scroll">
        {items.map(render)}
        {!items.length && <p className="kanban-empty">{empty}</p>}
      </div>
    </section>
  );
}

/** Draggable, focusable card. Enter opens it; Shift + ← / → moves it between columns. */
export function KanbanCard({
  id,
  draggable = false,
  onOpen,
  onMove,
  onDragState,
  children,
}: {
  id: string;
  draggable?: boolean;
  onOpen?: () => void;
  onMove?: (direction: -1 | 1) => void;
  onDragState?: (dragging: boolean) => void;
  children: ReactNode;
}) {
  return (
    <article
      className="kanban-card"
      tabIndex={0}
      draggable={draggable}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', id);
        onDragState?.(true);
      }}
      onDragEnd={() => onDragState?.(false)}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === 'Enter') {
          e.preventDefault();
          onOpen?.();
        } else if (e.shiftKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && onMove) {
          e.preventDefault();
          onMove(e.key === 'ArrowLeft' ? -1 : 1);
        }
      }}
    >
      {children}
    </article>
  );
}

export function KanbanCardTitle({ title, onClick }: { title: string; onClick: () => void }) {
  return (
    <button type="button" className="kanban-card-title" title={title} onClick={onClick}>
      {title}
    </button>
  );
}

export function KanbanCardText({ children }: { children: ReactNode }) {
  return <p className="kanban-card-text">{children}</p>;
}

export function KanbanCardMeta({ children }: { children: ReactNode }) {
  return <div className="kanban-card-meta">{children}</div>;
}
