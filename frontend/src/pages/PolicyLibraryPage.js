import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { FileText, Download, Eye, CaretRight, CheckCircle, Clock, Spinner } from "@phosphor-icons/react";

const CONTROL_FAMILY_NAMES = {
  AC: "Access Control",
  AT: "Awareness and Training",
  AU: "Audit and Accountability",
  CA: "Assessment, Authorization, and Monitoring",
  CM: "Configuration Management",
  CP: "Contingency Planning",
  IA: "Identification and Authentication",
  IR: "Incident Response",
  MA: "Maintenance",
  MP: "Media Protection",
  PE: "Physical and Environmental Protection",
  PL: "Planning",
  PM: "Program Management",
  PS: "Personnel Security",
  PT: "PII Processing and Transparency",
  RA: "Risk Assessment",
  SA: "System and Services Acquisition",
  SC: "System and Communications Protection",
  SI: "System and Information Integrity",
  SR: "Supply Chain Risk Management",
};

const PolicyLibraryPage = () => {
  const [generatedPolicies, setGeneratedPolicies] = useState([]);
  const [localPolicies, setLocalPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [policyContent, setPolicyContent] = useState(null);
  const [viewDialogOpen, setViewDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [activeTab, setActiveTab] = useState("generated");
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    fetchPolicies();
  }, []);

  const fetchPolicies = async () => {
    setLoading(true);
    try {
      // Fetch generated policies from Atlas
      const genResponse = await axios.get(`${API}/ironvision/generated-policies`);
      setGeneratedPolicies(genResponse.data.policies || []);
      
      // Fetch local policies
      const localResponse = await axios.get(`${API}/policies`);
      setLocalPolicies(localResponse.data || []);
    } catch (error) {
      console.error("Error fetching policies:", error);
      toast.error("Failed to fetch policies");
    } finally {
      setLoading(false);
    }
  };

  const viewPolicy = async (policy) => {
    setSelectedPolicy(policy);
    setViewDialogOpen(true);
    setPolicyContent(null);
    
    try {
      const response = await axios.get(`${API}/ironvision/generated-policies/${policy.id}`);
      setPolicyContent(response.data);
    } catch (error) {
      toast.error("Failed to load policy content");
    }
  };

  const exportPolicy = async (format) => {
    if (!selectedPolicy) return;
    
    setExporting(true);
    try {
      const response = await axios.get(
        `${API}/ironvision/generated-policies/${selectedPolicy.id}/export?format=${format}`
      );
      
      const { content, filename } = response.data;
      
      // Create download
      const blob = new Blob([content], { 
        type: format === 'html' ? 'text/html' : 'text/plain' 
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      toast.success(`Policy exported as ${format.toUpperCase()}`);
      setExportDialogOpen(false);
    } catch (error) {
      toast.error("Failed to export policy");
    } finally {
      setExporting(false);
    }
  };

  const renderPolicyContent = () => {
    if (!policyContent) {
      return (
        <div className="flex items-center justify-center h-64">
          <Spinner size={32} className="animate-spin text-[#2597B2]" />
        </div>
      );
    }

    const { content, generationMetadata } = policyContent;
    const header = content?.header || {};
    
    // Handle both formats: content.sections as array/dict or direct keys
    let sectionsToRender = [];
    const sections = content?.sections;
    
    if (sections && typeof sections === 'object' && !Array.isArray(sections)) {
      // New format: sections is an object with overview, roles, policy, etc.
      const sectionOrder = ['overview', 'roles', 'policy', 'procedures', 'enforcement', 'definitions', 'revisionHistory', 'approvals', 'distribution'];
      sectionOrder.forEach(key => {
        if (sections[key]) {
          sectionsToRender.push({ key, data: sections[key] });
        }
      });
    } else {
      // Old format: content has direct keys
      const sectionOrder = ['overview', 'roles', 'policy', 'procedures', 'enforcement', 'definitions', 'revisionHistory', 'approvals', 'distribution'];
      sectionOrder.forEach(key => {
        if (content?.[key]) {
          sectionsToRender.push({ key, data: content[key] });
        }
      });
    }
    
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="bg-gradient-to-r from-[#2597B2]/10 to-transparent p-6 rounded-lg border border-[#2597B2]/20">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">{header.title || policyContent.policyName}</h2>
          <div className="grid grid-cols-2 gap-4 text-sm text-gray-600">
            <p><span className="font-medium">Framework:</span> {policyContent.framework}</p>
            <p><span className="font-medium">Control Family:</span> {CONTROL_FAMILY_NAMES[policyContent.controlFamily] || policyContent.controlFamily}</p>
            <p><span className="font-medium">Version:</span> {policyContent.version}</p>
            <p><span className="font-medium">Status:</span> <span className="capitalize">{policyContent.status}</span></p>
          </div>
          {generationMetadata && (
            <div className="mt-4 pt-4 border-t border-[#2597B2]/20">
              <p className="text-xs text-gray-500">
                Generated using {generationMetadata.model || 'GPT-4'} 
                {generationMetadata.qualityScore && ` • Quality Score: ${generationMetadata.qualityScore}/100`}
                {generationMetadata.qualityLevel && ` (${generationMetadata.qualityLevel})`}
              </p>
            </div>
          )}
        </div>

        {/* Sections */}
        <div className="space-y-4">
          {sectionsToRender.map(({ key, data }) => {
            const sectionTitle = key === 'revisionHistory' ? 'Revision History' : 
                                key.charAt(0).toUpperCase() + key.slice(1);
            
            // Handle different data formats
            let subsections = [];
            let purposeContent = null;
            let scopeContent = null;
            let objectivesContent = null;
            
            if (typeof data === 'object') {
              subsections = data.subsections || [];
              purposeContent = data.purpose;
              scopeContent = data.scope;
              objectivesContent = data.objectives;
            }
            
            return (
              <div key={key} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
                  <h3 className="font-semibold text-gray-900">{sectionTitle}</h3>
                </div>
                <div className="p-4 space-y-4">
                  {/* Handle overview format with purpose, scope, objectives */}
                  {purposeContent && (
                    <div className="space-y-1">
                      <h4 className="font-medium text-gray-800 text-sm">Purpose</h4>
                      <p className="text-gray-600 text-sm leading-relaxed whitespace-pre-wrap">{purposeContent}</p>
                    </div>
                  )}
                  {scopeContent && (
                    <div className="space-y-1 mt-4">
                      <h4 className="font-medium text-gray-800 text-sm">Scope</h4>
                      <p className="text-gray-600 text-sm leading-relaxed whitespace-pre-wrap">{scopeContent}</p>
                    </div>
                  )}
                  {objectivesContent && Array.isArray(objectivesContent) && (
                    <div className="space-y-1 mt-4">
                      <h4 className="font-medium text-gray-800 text-sm">Objectives</h4>
                      <ul className="list-disc list-inside text-gray-600 text-sm space-y-1">
                        {objectivesContent.map((obj, idx) => (
                          <li key={idx}>{obj}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Handle subsections format */}
                  {subsections.map((sub, idx) => (
                    <div key={idx} className="space-y-1">
                      {sub.title && (
                        <h4 className="font-medium text-gray-800 text-sm">{sub.title}</h4>
                      )}
                      {sub.content && (
                        <p className="text-gray-600 text-sm leading-relaxed whitespace-pre-wrap">{sub.content}</p>
                      )}
                    </div>
                  ))}
                  
                  {subsections.length === 0 && !purposeContent && !scopeContent && !objectivesContent && (
                    <p className="text-gray-400 text-sm italic">No content in this section</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const filteredGenerated = generatedPolicies.filter(p => 
    p.policyName?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.controlFamily?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredLocal = localPolicies.filter(p =>
    p.title?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Layout>
      <div data-testid="policy-library-page">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>
              Policy Library
            </h1>
            <p className="text-sm text-gray-600 mt-2">
              View and export AI-generated compliance policies
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <Input
              placeholder="Search policies..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-64"
              data-testid="policy-search-input"
            />
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="generated" data-testid="generated-tab">
              AI Generated ({generatedPolicies.length})
            </TabsTrigger>
            <TabsTrigger value="local" data-testid="local-tab">
              Local Policies ({localPolicies.length})
            </TabsTrigger>
          </TabsList>

          {/* Generated Policies Tab */}
          <TabsContent value="generated">
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <Spinner size={32} className="animate-spin text-[#2597B2]" />
              </div>
            ) : filteredGenerated.length === 0 ? (
              <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
                <FileText size={48} weight="duotone" className="text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500 mb-2">No AI-generated policies yet</p>
                <p className="text-sm text-gray-400">
                  Use the Policy Builder to create NIST 800-53 compliant policies
                </p>
              </div>
            ) : (
              <div className="grid gap-4" data-testid="generated-policies-list">
                {filteredGenerated.map((policy) => (
                  <div 
                    key={policy.id}
                    className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-md hover:border-[#2597B2]/30 transition-all duration-200"
                    data-testid={`policy-card-${policy.id}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2">
                          <div className="w-10 h-10 bg-[#2597B2]/10 rounded-lg flex items-center justify-center">
                            <FileText size={20} weight="duotone" className="text-[#2597B2]" />
                          </div>
                          <div>
                            <h3 className="text-lg font-semibold text-gray-900">{policy.policyName}</h3>
                            <div className="flex items-center space-x-2 mt-1">
                              <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700">
                                {policy.framework}
                              </span>
                              <span className="px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-700">
                                {CONTROL_FAMILY_NAMES[policy.controlFamily] || policy.controlFamily}
                              </span>
                              <span className={`px-2 py-0.5 text-xs rounded-full flex items-center space-x-1 ${
                                policy.status === 'generated' || policy.status === 'draft' ? 'bg-green-100 text-green-700' :
                                policy.status === 'analyzed' ? 'bg-blue-100 text-blue-700' :
                                'bg-yellow-100 text-yellow-700'
                              }`}>
                                {policy.status === 'generated' || policy.status === 'draft' ? (
                                  <><CheckCircle size={12} weight="fill" /> <span>Generated</span></>
                                ) : (
                                  <><Clock size={12} /> <span>{policy.status}</span></>
                                )}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-4 text-xs text-gray-500 mt-3 ml-13">
                          {policy.companyName && <span>{policy.companyName}</span>}
                          <span>Version {policy.version || 1}</span>
                          {policy.qualityScore && (
                            <span className="text-[#2597B2]">Quality: {policy.qualityScore}/100</span>
                          )}
                          <span>Created {new Date(policy.createdAt).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => viewPolicy(policy)}
                          data-testid={`view-policy-${policy.id}`}
                        >
                          <Eye size={16} className="mr-1" />
                          View
                        </Button>
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => {
                            setSelectedPolicy(policy);
                            setExportDialogOpen(true);
                          }}
                          data-testid={`export-policy-${policy.id}`}
                        >
                          <Download size={16} className="mr-1" />
                          Export
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Local Policies Tab */}
          <TabsContent value="local">
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <Spinner size={32} className="animate-spin text-[#2597B2]" />
              </div>
            ) : filteredLocal.length === 0 ? (
              <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
                <FileText size={48} weight="duotone" className="text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">No local policies found</p>
              </div>
            ) : (
              <div className="space-y-4" data-testid="local-policies-list">
                {filteredLocal.map((policy) => (
                  <div 
                    key={policy.id}
                    className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-sm transition-all duration-200"
                    data-testid={`local-policy-card-${policy.id}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">{policy.title}</h3>
                          <span className={`px-2 py-1 text-xs rounded-full ${
                            policy.status === 'active' ? 'bg-green-100 text-green-700' :
                            policy.status === 'draft' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {policy.status}
                          </span>
                        </div>
                        <p className="text-sm text-gray-600 mb-3 line-clamp-2">{policy.content}</p>
                        <div className="flex items-center space-x-4 text-xs text-gray-500">
                          <span>Version {policy.version}</span>
                          <span>•</span>
                          <span>Created {new Date(policy.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <Button variant="outline" size="sm">View Details</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* View Policy Dialog */}
        <Dialog open={viewDialogOpen} onOpenChange={setViewDialogOpen}>
          <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="view-policy-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center justify-between">
                <span>{selectedPolicy?.policyName}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setExportDialogOpen(true);
                  }}
                >
                  <Download size={16} className="mr-1" />
                  Export
                </Button>
              </DialogTitle>
            </DialogHeader>
            <div className="mt-4">
              {renderPolicyContent()}
            </div>
          </DialogContent>
        </Dialog>

        {/* Export Dialog */}
        <Dialog open={exportDialogOpen} onOpenChange={setExportDialogOpen}>
          <DialogContent className="max-w-md" data-testid="export-policy-dialog">
            <DialogHeader>
              <DialogTitle>Export Policy</DialogTitle>
            </DialogHeader>
            <div className="mt-4 space-y-3">
              <p className="text-sm text-gray-600 mb-4">
                Choose a format to export "{selectedPolicy?.policyName}"
              </p>
              <Button
                className="w-full justify-start"
                variant="outline"
                onClick={() => exportPolicy('html')}
                disabled={exporting}
                data-testid="export-html-btn"
              >
                <CaretRight size={16} className="mr-2" />
                Export as HTML (Best for printing)
              </Button>
              <Button
                className="w-full justify-start"
                variant="outline"
                onClick={() => exportPolicy('markdown')}
                disabled={exporting}
                data-testid="export-md-btn"
              >
                <CaretRight size={16} className="mr-2" />
                Export as Markdown
              </Button>
              <Button
                className="w-full justify-start"
                variant="outline"
                onClick={() => exportPolicy('text')}
                disabled={exporting}
                data-testid="export-txt-btn"
              >
                <CaretRight size={16} className="mr-2" />
                Export as Plain Text
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default PolicyLibraryPage;
