import { AuthCard } from "@/components/auth/auth-card";
import { SignupForm } from "@/components/auth/signup-form";

export default function SignupPage() {
  return (
    <AuthCard title="Create account" description="Start with the free tier and local Supabase auth.">
      <SignupForm />
    </AuthCard>
  );
}
