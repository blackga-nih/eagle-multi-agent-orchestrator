import { redirect } from 'next/navigation';

/**
 * /packages → /workflows redirect.
 *
 * The canonical Acquisition Packages page lives at /workflows.
 * This redirect ensures the nav label "Packages" and any direct
 * /packages links resolve correctly.
 */
export default function PackagesRedirect() {
  redirect('/workflows');
}
