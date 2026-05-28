import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export default function ResetPasswordPage() {
  return (
    <AuthCard title="Reset password" description="Request a reset link or set a new password from the email link.">
      <Suspense fallback={<div className="text-sm text-muted-foreground">Loading reset form...</div>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthCard>
  );
}
