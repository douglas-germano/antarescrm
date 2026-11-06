import type { ReactNode } from 'react';
import { ArrowRightLeft, Bot, CalendarClock, CalendarPlus, CalendarX, FileInput, Instagram, KanbanSquare, ListChecks, MessageCircle, Reply, Send, Tag, Trophy, UserPlus, XCircle, Zap } from 'lucide-react';

const EVENT_ICONS: Record<string, ReactNode> = {
  'contact.created': <UserPlus size={15} />,
  'form.submitted': <FileInput size={15} />,
  'message.received': <MessageCircle size={15} />,
  'booking.created': <CalendarClock size={15} />,
  'booking.cancelled': <CalendarX size={15} />,
  'instagram.comment': <Instagram size={15} />,
  'opportunity.created': <KanbanSquare size={15} />,
  'opportunity.stage_changed': <ArrowRightLeft size={15} />,
  'opportunity.won': <Trophy size={15} />,
  'atlas.handoff': <Bot size={15} />,
  'opportunity.lost': <XCircle size={15} />,
};
const ACTION_ICONS: Record<string, ReactNode> = {
  atlas_assign: <Bot size={15} />,
  create_task: <ListChecks size={15} />,
  send_message: <Send size={15} />,
  follow_up: <CalendarPlus size={15} />,
  add_tag: <Tag size={15} />,
  move_stage: <ArrowRightLeft size={15} />,
  reply_comment: <Reply size={15} />,
  private_reply: <Instagram size={15} />,
  instagram_message: <Instagram size={15} />,
};
export const eventIcon = (event: string) => EVENT_ICONS[event] || <Zap size={15} />;
export const actionIcon = (kind: string) => ACTION_ICONS[kind] || <Zap size={15} />;
/** Instagram triggers and actions get the platform tint, like Gaio's channel badges. */
export const isInstagram = (key: string) => key.startsWith('instagram') || key === 'reply_comment' || key === 'private_reply' || key === 'instagram_message';
