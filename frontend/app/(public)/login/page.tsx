import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  return (
    <AuthCard title="Log in" description="Continue to your QSim Playground workspace.">
      <Suspense fallback={<div className="text-sm text-muted-foreground">Loading login form...</div>}>
        <LoginForm />
      </Suspense>
    </AuthCard>
  );
}
