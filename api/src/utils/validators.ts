export function isValidContactNumber(contactNumber: string): boolean {
  return /^\d{10}$/.test(contactNumber) && !/^0+$/.test(contactNumber);
}

export function isValidPersonalEmail(personalEmail: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(personalEmail);
}

export function isValidGithubProfile(githubProfile: string): boolean {
  return /^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_-]+$/.test(githubProfile);
}

export function isValidLinkedinProfile(linkedinProfile: string): boolean {
  return /^https?:\/\/(www\.)?linkedin\.com\/in\/[a-zA-Z0-9_-]+$/.test(
    linkedinProfile,
  );
}
