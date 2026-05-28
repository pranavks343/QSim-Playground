"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

const signupSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters.")
});

type FieldErrors = Partial<Record<"email" | "password" | "form", string>>;

export function SignupForm() {
  const router = useRouter();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [confirmationEmail, setConfirmationEmail] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const parsed = signupSchema.safeParse({
      email: formData.get("email"),
      password: formData.get("password")
    });
    if (!parsed.success) {
      setErrors(parsed.error.flatten().fieldErrors as FieldErrors);
      return;
    }
    setErrors({});
    startTransition(async () => {
      const supabase = createClient();
      const { data, error } = await supabase.auth.signUp({
        ...parsed.data,
        options:
          typeof window === "undefined"
            ? undefined
            : { emailRedirectTo: `${window.location.origin}/dashboard` }
      });
      if (error) {
        const message = normalizeSignupError(error.message);
        setErrors({ form: message });
        toast.error(message);
        return;
      }
      if (data.session === null) {
        setConfirmationEmail(parsed.data.email);
        toast.success("Check your email to confirm your account.");
        return;
      }
      toast.success("Account created");
      router.push("/dashboard");
      router.refresh();
    });
  };

  if (confirmationEmail !== null) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border bg-card p-4">
          <h2 className="text-base font-semibold">Check your email to confirm</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            We sent a confirmation link to{" "}
            <span className="font-medium text-foreground">{confirmationEmail}</span>. Open it to
            finish creating your QSim Playground account.
          </p>
        </div>
        <Button variant="outline" className="w-full" asChild>
          <Link href="/login">Back to login</Link>
        </Button>
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" autoComplete="email" aria-invalid={Boolean(errors.email)} />
        {errors.email ? <p className="text-sm text-destructive">{errors.email}</p> : null}
      </div>
      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          aria-invalid={Boolean(errors.password)}
        />
        <p className="text-xs text-muted-foreground">Use 8+ characters. Longer passphrases work best.</p>
        {errors.password ? <p className="text-sm text-destructive">{errors.password}</p> : null}
      </div>
      {errors.form ? <p className="text-sm text-destructive">{errors.form}</p> : null}
      <Button className="w-full" disabled={isPending}>
        {isPending ? "Creating account..." : "Sign up"}
      </Button>
      <p className="text-sm text-muted-foreground">
        Already have an account? <Link href="/login">Log in</Link>
      </p>
    </form>
  );
}

function normalizeSignupError(message: string) {
  const lower = message.toLowerCase();
  if (lower.includes("already") || lower.includes("registered")) {
    return "That email is already registered. Try logging in instead.";
  }
  if (lower.includes("password")) {
    return "Supabase rejected this password. Try a stronger one.";
  }
  return message;
}
