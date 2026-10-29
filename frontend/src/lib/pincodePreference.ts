const storageKey = "costiqo-pincode-preference";

export type PincodePreference = {
  pincode: string;
  location: string | null;
};

export function readPincodePreference(): PincodePreference | null {
  const raw = localStorage.getItem(storageKey);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<PincodePreference>;
    if (typeof parsed.pincode !== "string" || !parsed.pincode.trim()) {
      return null;
    }
    return {
      pincode: parsed.pincode.trim(),
      location: typeof parsed.location === "string" && parsed.location.trim()
        ? parsed.location.trim()
        : null,
    };
  } catch {
    return null;
  }
}

export function writePincodePreference(preference: PincodePreference) {
  localStorage.setItem(storageKey, JSON.stringify(preference));
}

export function clearPincodePreference() {
  localStorage.removeItem(storageKey);
}
