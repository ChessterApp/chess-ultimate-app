'use client';

import { useState, useEffect } from 'react';

let cachedHealth: boolean | null = null;
let lastCheck = 0;
const CHECK_INTERVAL = 60000; // 1 minute

export function useBackendHealth() {
  const [isHealthy, setIsHealthy] = useState<boolean | null>(cachedHealth);

  useEffect(() => {
    const now = Date.now();
    if (cachedHealth !== null && now - lastCheck < CHECK_INTERVAL) {
      setIsHealthy(cachedHealth);
      return;
    }

    const checkHealth = async () => {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);

        const res = await fetch('/api/health', {
          signal: controller.signal,
        });
        clearTimeout(timeout);

        const healthy = res.ok;
        cachedHealth = healthy;
        lastCheck = Date.now();
        setIsHealthy(healthy);
      } catch {
        cachedHealth = false;
        lastCheck = Date.now();
        setIsHealthy(false);
      }
    };

    checkHealth();
  }, []);

  return isHealthy;
}
