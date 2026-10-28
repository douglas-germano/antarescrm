import { useEffect, useLayoutEffect, useRef } from 'react';

const NEAR_BOTTOM = 120;

/**
 * Keeps a chat scrolled to its last message: jumps there when a conversation opens, follows new messages,
 * and stays there while photos and videos finish loading. Scrolling up to read history stops the following
 * until the reader comes back near the bottom.
 */
export function useStickToBottom(conversationKey: string, lastMessageKey?: string, ready = true) {
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const toBottom = () => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  // A newly opened conversation always starts at its latest message.
  useLayoutEffect(() => { pinned.current = true; }, [conversationKey]);
  useLayoutEffect(() => { if (ready && pinned.current) toBottom(); }, [conversationKey, lastMessageKey, ready]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onScroll = () => { pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM; };
    // Media loads after the first scroll and pushes the last message down; follow it while pinned.
    const onLoad = () => { if (pinned.current) toBottom(); };
    el.addEventListener('scroll', onScroll, { passive: true });
    el.addEventListener('load', onLoad, true);
    el.addEventListener('loadedmetadata', onLoad, true);
    return () => {
      el.removeEventListener('scroll', onScroll);
      el.removeEventListener('load', onLoad, true);
      el.removeEventListener('loadedmetadata', onLoad, true);
    };
  }, [ready]);

  return box;
}
