import CredentialsManager from "../components/CredentialsManager";

export default function SettingsPage() {
  return (
    <main className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Manage credentials the orchestrator uses at run time. Values are
          masked in the list and revealed on demand for copying.
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-base font-semibold">Credentials</h2>
        <CredentialsManager />
      </section>
    </main>
  );
}
