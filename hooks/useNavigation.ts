import { useCallback, useState } from 'react';
import { View } from '../types';

export function useNavigation(initialView: View = View.SPLASH) {
  const [currentView, setCurrentView] = useState<View>(initialView);
  const [isTransitioning, setIsTransitioning] = useState(false);

  const navigate = useCallback((view: View) => {
    setCurrentView(view);
  }, []);

  return {
    currentView,
    setCurrentView,
    navigate,
    isTransitioning,
    setIsTransitioning,
  };
}

