import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Sparkle, ChartLine } from "@phosphor-icons/react";

const AnalyticsPage = () => {
  const [predictions, setPredictions] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchPredictions = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API}/analytics/predict`, {});
      setPredictions(response.data.predictions);
      toast.success("AI predictions generated");
    } catch (error) {
      toast.error("Failed to generate predictions");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div data-testid="analytics-page">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>AI-Driven Analytics</h1>
          <p className="text-sm text-gray-600 mt-2">Predictive insights and compliance recommendations</p>
        </div>

        <div className="grid grid-cols-1 gap-6">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-center space-x-2 mb-4">
              <Sparkle size={24} weight="duotone" className="text-[#2597B2]" />
              <h2 className="text-xl font-semibold text-gray-900" style={{fontFamily: 'Inter, sans-serif'}}>Predictive Compliance Analysis</h2>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Use AI to analyze your organization's compliance data and predict potential issues before they arise.
            </p>
            <Button 
              onClick={fetchPredictions} 
              disabled={loading}
              className="bg-[#2597B2] hover:bg-[#1B839F]"
              data-testid="generate-predictions-button"
            >
              {loading ? (
                <><Sparkle size={20} weight="fill" className="mr-2 animate-pulse" />Analyzing...</>
              ) : (
                <><Sparkle size={20} weight="duotone" className="mr-2" />Generate AI Predictions</>
              )}
            </Button>

            {predictions && (
              <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg" data-testid="predictions-result">
                <h3 className="font-semibold text-blue-900 mb-2 flex items-center">
                  <ChartLine size={20} weight="fill" className="mr-2" />
                  AI Predictions & Recommendations
                </h3>
                <pre className="text-sm text-blue-800 whitespace-pre-wrap">{predictions}</pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default AnalyticsPage;