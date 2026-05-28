"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password.")
});

type FieldErrors = Partial<Record<"email" | "password" | "form", string>>;

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [isPending, startTransition] = useTransition();

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const parsed = loginSchema.safeParse({
      email: formData.get("email"),
      password: formData.get("password")
    });
    if (!parsed.success) {
      setErrors(parsed.error.flatten().fieldErrors as FieldErrors);
      return;
    }
    setErrors({});
    startTransition(async () => {
      const { error } = await createClient().auth.signInWithPassword(parsed.data);
      if (error) {
        const message = "Invalid email or password.";
        setErrors({ form: message });
        toast.error(message);
        return;
      }
      const returnUrl = searchParams.get("returnUrl") ?? searchParams.get("next") ?? "/dashboard";
      router.push(safeReturnUrl(returnUrl));
      router.refresh();
    });
  };

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
          autoComplete="current-password"
          aria-invalid={Boolean(errors.password)}
        />
        {errors.password ? <p className="text-sm text-destructive">{errors.password}</p> : null}
      </div>
      {errors.form ? <p className="text-sm text-destructive">{errors.form}</p> : null}
      <Button className="w-full" disabled={isPending}>
        {isPending ? "Signing in..." : "Log in"}
      </Button>
      <div className="flex justify-between text-sm text-muted-foreground">
        <Link href="/reset-password">Forgot password?</Link>
        <Link href="/signup">Create account</Link>
      </div>
    </form>
  );
}

function safeReturnUrl(value: string) {
  return value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}
