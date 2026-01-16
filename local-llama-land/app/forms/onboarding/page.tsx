import { OnboardingForm } from '../../../components/client/onboarding-form';

export default function OnboardingPage() {
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Multi-step form</h1>
        <p className="text-white/70">
          Built to exercise validation + state-aware assertions (disabled → enabled buttons).
        </p>
      </div>
      <OnboardingForm />
    </div>
  );
}

