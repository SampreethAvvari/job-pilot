// Client-safe: deterministic people-search links for finding the real recipient
// and their email by hand (the free Apollo plan returns no verified emails).

export type PeopleLink = { label: string; url: string };

const ROLES = [
  "technical recruiter",
  "recruiter",
  "talent acquisition",
  "hiring manager",
  "engineering manager",
];

export function findPeopleLinks(company: string): PeopleLink[] {
  const c = company.trim();
  const links: PeopleLink[] = ROLES.map((role) => ({
    label: role,
    url: `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`"${c}" ${role}`)}`,
  }));
  links.push({
    label: "Apollo",
    url: `https://app.apollo.io/#/people?qOrganizationName=${encodeURIComponent(c)}`,
  });
  links.push({
    label: "Google",
    url: `https://www.google.com/search?q=${encodeURIComponent(`${c} recruiter email`)}`,
  });
  return links;
}
