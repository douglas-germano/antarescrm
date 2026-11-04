import { useEffect, useState } from 'react';
import { useRouterState } from '@tanstack/react-router';

export function NavigationProgress() {
  const pending = useRouterState({ select: state => state.status === 'pending' });
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!pending) { setVisible(false); return; }
    const timer = setTimeout(() => setVisible(true), 180);
    return () => clearTimeout(timer);
  }, [pending]);
  return pending && visible ? <div className="navigation-progress" role="progressbar" aria-label="Abrindo tela" /> : null;
}
