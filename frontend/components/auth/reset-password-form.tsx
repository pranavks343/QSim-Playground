"use client";

import { useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

const emailSchema = z.object({ email: z.string().email("Enter a valid email address.") });
const passwordSchema = z.object({
  password: z.string().min(8, "Password must be at least 8 characters.")
});

export function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const mode = searchParams.has("code") || searchParams.get("type") === "recovery" ? "update" : "request";
  return mode === "update" ? <UpdatePasswordForm /> : <RequestResetForm />;
}

function RequestResetForm() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setError(null);
    const parsed = emailSchema.safeParse({ email: new FormData(event.currentTarget).get("email") });
    if (!parsed.success) {
      setError(parsed.error.flatten().fieldErrors.email?.[0] ?? "Enter a valid email.");
      return;
    }
    startTransition(async () => {
      const redirectTo = `${window.location.origin}/reset-password`;
      const { error: resetError } = await createClient().auth.resetPasswordForEmail(parsed.data.email, {
        redirectTo
      });
      if (resetError) {
        setError(resetError.message);
        toast.error(resetError.message);
        return;
      }
      setMessage("Password reset email sent.");
      toast.success("Password reset email sent");
    });
  };

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" autoComplete="email" />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {message ? <p className="text-sm text-success">{message}</p> : null}
      <Button className="w-full" disabled={isPending}>
        {isPending ? "Sending..." : "Send reset link"}
      </Button>
    </form>
  );
}

function UpdatePasswordForm() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setError(null);
    const parsed = passwordSchema.safeParse({
      password: new FormData(event.currentTarget).get("password")
    });
    if (!parsed.success) {
      setError(parsed.error.flatten().fieldErrors.password?.[0] ?? "Enter a stronger password.");
      return;
    }
    startTransition(async () => {
      const { error: updateError } = await createClient().auth.updateUser({
        password: parsed.data.password
      });
      if (updateError) {
        setError(updateError.message);
        toast.error(updateError.message);
        return;
      }
      setMessage("Password updated. You can now sign in.");
      toast.success("Password updated");
    });
  };

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <div className="space-y-2">
        <Label htmlFor="password">New password</Label>
        <Input id="password" name="password" type="password" autoComplete="new-password" />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {message ? <p className="text-sm text-success">{message}</p> : null}
      <Button className="w-full" disabled={isPending}>
        {isPending ? "Updating..." : "Update password"}
      </Button>
    </form>
  );
}
