import { useState, useCallback, useEffect } from "react";

const STORAGE_KEY = "boke_history";
const MAX_HISTORY = 50;

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveHistory(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

export function useHistory() {
  const [history, setHistory] = useState(loadHistory);

  useEffect(() => {
    saveHistory(history);
  }, [history]);

  const addHistory = useCallback((item) => {
    setHistory((prev) => {
      const next = [{ ...item, time: Date.now() }, ...prev];
      if (next.length > MAX_HISTORY) next.pop();
      return next;
    });
  }, []);

  const removeHistory = useCallback((id) => {
    setHistory((prev) => prev.filter((h) => h.id !== id));
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  return { history, addHistory, removeHistory, clearHistory };
}
