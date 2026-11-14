// Measures WCAG contrast for every visible piece of text on the current page.
// The background is the real stack behind the text: translucent layers (glass cards, tints)
// are composited over whatever sits below them until an opaque colour is reached.
export function auditContrast(options = {}) {
  const { root = 'body', ignore = [] } = options;
  const parse = value => {
    const match = /rgba?\(([^)]+)\)/.exec(value || '');
    if (!match) return null;
    const parts = match[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  };
  const over = (top, bottom) => {
    const a = top.a + bottom.a * (1 - top.a);
    if (!a) return { r: 0, g: 0, b: 0, a: 0 };
    const mix = key => (top[key] * top.a + bottom[key] * bottom.a * (1 - top.a)) / a;
    return { r: mix('r'), g: mix('g'), b: mix('b'), a };
  };
  const scale = (color, factor) => ({ ...color, a: color.a * factor });
  // Gradients count as the average of their stops; good enough for the subtle glass sheen.
  const gradient = image => {
    const stops = [...image.matchAll(/rgba?\([^)]+\)/g)].map(match => parse(match[0]));
    if (!stops.length) return null;
    const sum = stops.reduce((acc, stop) => ({ r: acc.r + stop.r * stop.a, g: acc.g + stop.g * stop.a, b: acc.b + stop.b * stop.a, a: acc.a + stop.a }), { r: 0, g: 0, b: 0, a: 0 });
    return sum.a ? { r: sum.r / sum.a, g: sum.g / sum.a, b: sum.b / sum.a, a: sum.a / stops.length } : null;
  };
  const luminance = ({ r, g, b }) => {
    const channel = value => { const v = value / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const ratio = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const layers = element => {
    const stack = [];
    let opacity = 1;
    for (let node = element; node && node.nodeType === 1; node = node.parentElement) {
      const style = getComputedStyle(node);
      opacity *= Number(style.opacity);
      const image = style.backgroundImage && style.backgroundImage !== 'none' ? gradient(style.backgroundImage) : null;
      const color = parse(style.backgroundColor);
      if (image && /url\(/.test(style.backgroundImage)) return { stack, opacity, unknown: true };
      if (image) stack.push(image);
      if (color && color.a > 0) stack.push(color);
      if (stack.some(layer => layer.a >= 0.999)) break;
    }
    return { stack, opacity, unknown: false };
  };
  const background = element => {
    const { stack, opacity, unknown } = layers(element);
    if (unknown) return { unknown };
    let color = { r: 255, g: 255, b: 255, a: 1 };
    for (const layer of stack.reverse()) color = over(layer, color);
    return { color, opacity };
  };
  const visible = element => {
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) return false;
    const style = getComputedStyle(element);
    return style.visibility !== 'hidden' && style.display !== 'none';
  };
  const describe = element => {
    const name = element.tagName.toLowerCase();
    const classes = typeof element.className === 'string' && element.className.trim() ? '.' + element.className.trim().split(/\s+/).join('.') : '';
    const parent = element.parentElement;
    const parentClasses = parent && typeof parent.className === 'string' && parent.className.trim() ? parent.className.trim().split(/\s+/)[0] : parent?.tagName.toLowerCase();
    return `${parentClasses} > ${name}${classes}`;
  };
  const hex = color => '#' + [color.r, color.g, color.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const failures = [];
  const seen = new Set();
  const scope = document.querySelector(root) || document.body;
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const text = walker.currentNode.textContent.trim();
    const element = walker.currentNode.parentElement;
    if (!text || !element || seen.has(element)) continue;
    seen.add(element);
    if (element.closest('[aria-hidden="true"], svg, script, style, noscript, option, .skip-link')) continue;
    if (element.closest(':disabled, [aria-disabled="true"]')) continue; // WCAG exempts inactive controls.
    if (ignore.some(selector => element.closest(selector))) continue;
    if (!visible(element)) continue;
    const style = getComputedStyle(element);
    const foreground = parse(style.color);
    if (!foreground) continue;
    const behind = background(element);
    if (behind.unknown || foreground.a < 0.05 || behind.opacity < 0.1) continue;
    const ink = over(scale(foreground, behind.opacity), behind.color);
    const size = parseFloat(style.fontSize);
    const bold = Number(style.fontWeight) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const minimum = large ? 3 : 4.5;
    const measured = ratio(ink, behind.color);
    if (measured + 0.005 < minimum) {
      failures.push({ where: describe(element), text: text.slice(0, 40), ratio: Math.round(measured * 100) / 100, minimum, color: hex(ink), background: hex(behind.color) });
    }
  }
  // Icon-only controls carry their meaning in the icon: WCAG asks 3:1 for those graphics.
  for (const control of scope.querySelectorAll('button, a, [role="button"], [role="switch"]')) {
    if (control.textContent.trim() || !visible(control)) continue;
    if (control.closest(':disabled, [aria-disabled="true"], [aria-hidden="true"]')) continue;
    if (ignore.some(selector => control.closest(selector))) continue;
    const icon = control.querySelector('svg');
    if (!icon || !visible(icon)) continue;
    const foreground = parse(getComputedStyle(icon).color);
    const behind = background(icon);
    if (!foreground || behind.unknown) continue;
    // Faded-out row actions and unticked checkmarks are hidden on purpose until hover or use.
    if (foreground.a < 0.05 || behind.opacity < 0.1) continue;
    const ink = over(scale(foreground, behind.opacity), behind.color);
    const measured = ratio(ink, behind.color);
    if (measured + 0.005 < 3) {
      failures.push({ where: describe(control) + ' (ícone)', text: control.getAttribute('aria-label') || '', ratio: Math.round(measured * 100) / 100, minimum: 3, color: hex(ink), background: hex(behind.color) });
    }
  }
  return failures;
}
