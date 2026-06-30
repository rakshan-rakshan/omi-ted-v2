"use client";
import { useEffect, useState } from "react";

/**
 * Viewport-aware breakpoints for conditional rendering (mobile < 768,
 * tablet 768–1023, desktop ≥ 1024). `mounted` is false until the client
 * hydrates — render desktop defaults until then to avoid hydration mismatch.
 */
export function useBreakpoint() {
  const [width, setWidth] = useState<number>(1280);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    onResize();
    setMounted(true);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return {
    width,
    mounted,
    isMobile: mounted && width < 768,
    isTablet: mounted && width >= 768 && width < 1024,
    isDesktop: !mounted || width >= 1024,
  };
}
