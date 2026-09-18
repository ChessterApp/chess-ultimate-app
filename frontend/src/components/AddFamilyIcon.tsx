/** Person-plus glyph for the avatar-menu "Добавить члена семьи" sub-view.
 *  Shared by both UserButton instances (Navbar + DesktopSidebar) so the custom
 *  family action renders identically on mobile and desktop. */
export default function AddFamilyIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M15 19a6 6 0 0 0-12 0M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM19 8v6M22 11h-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
