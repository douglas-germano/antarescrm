import { useEffect, useRef } from 'react';

const margin = 8;
const gap = 8;

function triggerFor(target: EventTarget | null) {
  return target instanceof Element ? target.closest<HTMLElement>('[data-tip]') : null;
}

// Render one tooltip in the top layer so tables, scroll containers and dialogs cannot clip it.
export function ActionTooltip() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tooltip = ref.current!;
    let trigger: HTMLElement | null = null;
    let timer: number | undefined;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.target === trigger && !entry.isIntersecting)) hide();
    });

    function hide() {
      window.clearTimeout(timer);
      observer.disconnect();
      trigger = null;
      tooltip.hidePopover?.();
      tooltip.hidden = true;
    }

    function positionTooltip() {
      if (!trigger || tooltip.hidden) return;
      const anchor = trigger.getBoundingClientRect();
      const { offsetWidth: width, offsetHeight: height } = tooltip;
      const { clientWidth, clientHeight } = document.documentElement;
      const center = anchor.left + anchor.width / 2;
      const alignment = trigger.dataset.tipAlign;
      const preferredLeft = alignment === 'start' ? anchor.left
        : alignment === 'end' ? anchor.right - width
        : center - width / 2;
      const left = Math.max(margin, Math.min(preferredLeft, clientWidth - width - margin));
      const above = anchor.top - gap - height;
      const below = anchor.bottom + gap;
      const fitsAbove = above >= margin;
      const fitsBelow = below + height <= clientHeight - margin;
      const placeBelow = fitsBelow && (!fitsAbove || Boolean(trigger.closest('.tips-below')));
      const top = Math.max(margin, Math.min(placeBelow ? below : above, clientHeight - height - margin));

      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
      tooltip.style.setProperty('--arrow-left', `${Math.max(8, Math.min(center - left, width - 8))}px`);
      tooltip.dataset.side = placeBelow ? 'below' : 'above';
    }

    function show(next: HTMLElement | null) {
      if (next === trigger) return;
      hide();
      if (!next?.dataset.tip) return;
      trigger = next;
      observer.observe(next);
      timer = window.setTimeout(() => {
        const label = next.dataset.tip;
        if (!next.isConnected || !label) {
          hide();
          return;
        }
        tooltip.textContent = label;
        tooltip.hidden = false;
        tooltip.showPopover?.();
        positionTooltip();
      }, 150);
    }

    function pointerOver(event: PointerEvent) {
      if (event.pointerType !== 'touch') show(triggerFor(event.target));
    }

    function pointerOut(event: PointerEvent) {
      if (trigger && triggerFor(event.target) === trigger && triggerFor(event.relatedTarget) !== trigger) hide();
    }

    function focusIn(event: FocusEvent) {
      if (event.target instanceof Element && event.target.matches(':focus-visible')) show(triggerFor(event.target));
    }

    function focusOut(event: FocusEvent) {
      if (trigger && triggerFor(event.target) === trigger && triggerFor(event.relatedTarget) !== trigger) hide();
    }

    function keyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && trigger) hide();
    }

    document.addEventListener('pointerover', pointerOver, true);
    document.addEventListener('pointerout', pointerOut, true);
    document.addEventListener('focusin', focusIn);
    document.addEventListener('focusout', focusOut);
    document.addEventListener('keydown', keyDown);
    document.addEventListener('scroll', positionTooltip, true);
    document.addEventListener('pointerdown', hide, true);
    window.addEventListener('resize', positionTooltip);

    return () => {
      hide();
      document.removeEventListener('pointerover', pointerOver, true);
      document.removeEventListener('pointerout', pointerOut, true);
      document.removeEventListener('focusin', focusIn);
      document.removeEventListener('focusout', focusOut);
      document.removeEventListener('keydown', keyDown);
      document.removeEventListener('scroll', positionTooltip, true);
      document.removeEventListener('pointerdown', hide, true);
      window.removeEventListener('resize', positionTooltip);
    };
  }, []);

  return <div ref={ref} className="action-tooltip" popover="manual" role="tooltip" hidden />;
}
