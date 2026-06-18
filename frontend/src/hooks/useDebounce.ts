import { useEffect, useState } from 'react';

/**
 * Returns a debounced copy of `value` that only settles after `delay`ms of no
 * changes. Keeps high-frequency input (search keystrokes) from firing a request
 * / react-query key change on every character.
 */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
