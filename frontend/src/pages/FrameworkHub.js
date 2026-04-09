import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import Layout from "@/components/Layout";
import FrameworksPage from "@/pages/FrameworksPage";

const FrameworkHub = () => {
  return (
    <Layout>
      <div data-testid="framework-hub-page">
        <FrameworksPage embedded />
      </div>
    </Layout>
  );
};

export default FrameworkHub;
