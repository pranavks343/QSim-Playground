import { createClient } from "@/lib/supabase/server";

import { NavClient } from "./nav-client";

export async function Nav() {
  const supabase = createClient();
  const {
    data: { user }
  } = supabase === null ? { data: { user: null } } : await supabase.auth.getUser();

  return <NavClient isAuthenticated={user !== null} email={user?.email ?? null} />;
}
