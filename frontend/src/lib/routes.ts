// Claim pages take the id as a query parameter: /app/claims/view?id=5 is a static page served from the CDN edge,
// while /app/claims/[id] made every visit wait for a serverless render in a US region (D28).
export const claimHref = (id: number | string) => `/app/claims/view?id=${id}`;
export const reviewHref = (id: number | string) => `/finance/review/view?id=${id}`;
