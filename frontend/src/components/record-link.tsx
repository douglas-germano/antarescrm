import { Link } from '@tanstack/react-router';
import type { AnchorHTMLAttributes } from 'react';
import { parseSearch } from '@/lib/search';

/** Links supplied by records and notifications arrive as complete URLs, including search and hash. */
export function RecordLink({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  if (/^(?:[a-z][\w+.-]*:|\/\/)/i.test(href)) return <a href={href} {...props} />;
  const url = new URL(href, 'http://antares.internal');
  return <Link to={url.pathname} search={() => parseSearch(url.search)} hash={url.hash.slice(1)} {...props} />;
}
