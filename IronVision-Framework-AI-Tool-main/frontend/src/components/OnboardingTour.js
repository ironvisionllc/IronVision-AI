import React, { useState, useEffect, useContext } from "react";
import { Joyride, STATUS } from "react-joyride";
import { useLocation } from "react-router-dom";
import { AuthContext } from "@/App";

const TOUR_STEPS = [
  {
    target: '[data-testid="compliance-score-hero"]',
    content: "Your overall compliance posture at a glance. This score aggregates control mapping coverage across all your frameworks.",
    title: "Compliance Score",
    disableBeacon: true,
    placement: "bottom",
  },
  {
    target: '[data-testid="stat-policies"]',
    content: "Quick metrics showing your policies, control mappings, open risks, audits, tasks, and vendors in one row.",
    title: "Key Metrics",
    placement: "bottom",
  },
  {
    target: '[data-testid="framework-compliance-chart"]',
    content: "See how well each compliance framework is covered. The bar length shows the percentage of controls with mapped policies.",
    title: "Framework Compliance",
    placement: "right",
  },
  {
    target: '[data-testid="risk-distribution-chart"]',
    content: "Visualize your risk landscape by severity. Critical and high risks are highlighted for immediate attention.",
    title: "Risk Distribution",
    placement: "left",
  },
  {
    target: '[data-testid="nav-frameworks"]',
    content: "Explore 11 pre-loaded compliance frameworks (NIST, ISO, HIPAA, SOC 2, GDPR, and more) with 660+ controls.",
    title: "Frameworks & Controls",
    placement: "right",
  },
  {
    target: '[data-testid="nav-policies"]',
    content: "Create and manage compliance policies. Use AI-powered mapping to automatically link policies to framework controls.",
    title: "Policy Management",
    placement: "right",
  },
  {
    target: '[data-testid="nav-risks"]',
    content: "Maintain your risk register with likelihood and impact scoring. Track risk status from open through mitigation to closure.",
    title: "Risk Register",
    placement: "right",
  },
  {
    target: '[data-testid="nav-tasks"]',
    content: "Track compliance tasks and remediation workflows. Assign tasks, set priorities, and monitor progress across your team.",
    title: "Task Management",
    placement: "right",
  },
  {
    target: '[data-testid="nav-evidence"]',
    content: "Central evidence library for storing audit artifacts, attestations, screenshots, and compliance documentation.",
    title: "Evidence Library",
    placement: "right",
  },
  {
    target: '[data-testid="nav-integrations"]',
    content: "Connect with tools like Slack, Jira, and SIEM solutions to streamline your compliance workflows.",
    title: "Integrations Hub",
    placement: "right",
  },
];

const TOUR_STYLES = {
  options: {
    primaryColor: "#2597B2",
    textColor: "#111827",
    backgroundColor: "#FFFFFF",
    arrowColor: "#FFFFFF",
    overlayColor: "rgba(0, 0, 0, 0.4)",
    zIndex: 10000,
  },
  tooltip: {
    borderRadius: 12,
    padding: "20px 24px",
    fontSize: 14,
    boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
  },
  tooltipTitle: {
    fontSize: 16,
    fontWeight: 700,
    fontFamily: "Inter, sans-serif",
    marginBottom: 8,
  },
  tooltipContent: {
    lineHeight: 1.6,
    color: "#4B5563",
  },
  buttonNext: {
    backgroundColor: "#2597B2",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    padding: "8px 20px",
  },
  buttonBack: {
    color: "#4B5563",
    fontSize: 13,
    fontWeight: 600,
    marginRight: 8,
  },
  buttonSkip: {
    color: "#9CA3AF",
    fontSize: 12,
  },
  spotlight: {
    borderRadius: 12,
  },
};

const OnboardingTour = () => {
  const { user } = useContext(AuthContext);
  const location = useLocation();
  const [run, setRun] = useState(false);
  const [hasLaunched, setHasLaunched] = useState(false);

  useEffect(() => {
    // Only launch once, only on /dashboard, only for demo users who haven't seen it
    if (
      user?.is_demo &&
      location.pathname === "/dashboard" &&
      !hasLaunched &&
      !localStorage.getItem("grc_tour_done")
    ) {
      const timer = setTimeout(() => {
        setRun(true);
        setHasLaunched(true);
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [user, location.pathname, hasLaunched]);

  const handleCallback = (data) => {
    const { status } = data;
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      setRun(false);
      localStorage.setItem("grc_tour_done", "true");
    }
  };

  if (!run) return null;

  return (
    <Joyride
      steps={TOUR_STEPS}
      run={run}
      continuous
      showSkipButton
      showProgress
      scrollToFirstStep
      disableOverlayClose
      disableBeacon
      callback={handleCallback}
      styles={TOUR_STYLES}
      locale={{
        back: "Back",
        close: "Close",
        last: "Finish Tour",
        next: "Next",
        skip: "Skip Tour",
      }}
    />
  );
};

export default OnboardingTour;
