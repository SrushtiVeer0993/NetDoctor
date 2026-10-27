import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Login failed. Check your credentials.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <Link to="/" className="font-mono text-healthy tracking-wide">NETDOCTOR</Link>
        </div>
        <form onSubmit={handleSubmit} className="rounded-lg border border-border bg-panel p-6 space-y-4">
          <h1 className="text-lg font-medium text-slate-100">Log in</h1>

          {error && (
            <div className="text-sm text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <div>
            <label className="text-xs text-slate-500">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
          </div>

          <div>
            <label className="text-xs text-slate-500">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-healthy text-black font-medium rounded-md py-2 text-sm hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Logging in…" : "Log in"}
          </button>

          <div className="text-center text-xs text-slate-500">
            No account?{" "}
            <Link to="/register" className="text-healthy hover:underline">
              Register
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
