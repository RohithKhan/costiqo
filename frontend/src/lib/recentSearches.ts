export type RecentSearch = {
  query: string;
  pincode: string;
  createdAt: string;
};

const maxRecentSearches = 10;
const storagePrefix = "costiqo-recent-searches";

function storageKey(userId: number | string | null | undefined) {
  return `${storagePrefix}:${userId ?? "guest"}`;
}

function parseRecentSearches(value: string | null): RecentSearch[] {
  if (!value) {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as RecentSearch[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item) => item?.query && item?.createdAt);
  } catch {
    return [];
  }
}

export function readRecentSearches(userId: number | string | null | undefined) {
  if (typeof window === "undefined") {
    return [];
  }
  return parseRecentSearches(localStorage.getItem(storageKey(userId))).slice(0, maxRecentSearches);
}

export function addRecentSearch(
  userId: number | string | null | undefined,
  item: Pick<RecentSearch, "query" | "pincode">,
) {
  if (typeof window === "undefined") {
    return [];
  }

  const query = item.query.trim();
  if (!query) {
    return readRecentSearches(userId);
  }

  const pincode = item.pincode.trim();
  const nextItem: RecentSearch = {
    query,
    pincode,
    createdAt: new Date().toISOString(),
  };
  const normalizedQuery = query.toLowerCase();
  const existing = readRecentSearches(userId).filter(
    (recent) => recent.query.trim().toLowerCase() !== normalizedQuery,
  );
  const next = [nextItem, ...existing].slice(0, maxRecentSearches);
  localStorage.setItem(storageKey(userId), JSON.stringify(next));
  return next;
}

export function formatRecentSearchTime(value: string) {
  const createdAt = new Date(value).getTime();
  if (!Number.isFinite(createdAt)) {
    return "";
  }

  const diffMs = Date.now() - createdAt;
  const diffMinutes = Math.max(0, Math.floor(diffMs / 60_000));
  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  }

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) {
    return "Yesterday";
  }
  if (diffDays < 7) {
    return `${diffDays} days ago`;
  }
  return `${Math.floor(diffDays / 7)} week${diffDays < 14 ? "" : "s"} ago`;
}
