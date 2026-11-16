// Extension points that later modules fill (LIB-UI-MEM-03: "screens of later modules add parts to this page").

/** Parts of the member page: {id, render(ctx, member) → Node|Promise<Node>}; staff only. */
export const memberPageParts = [];

/** Parts of the book page: {id, render(ctx, book) → Node|Promise<Node>}. */
export const bookPageParts = [];
