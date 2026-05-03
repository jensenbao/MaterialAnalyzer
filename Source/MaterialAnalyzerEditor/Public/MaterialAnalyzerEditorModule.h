#pragma once

#include "Modules/ModuleManager.h"

class FMaterialAnalyzerEditorModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void RegisterMenus();
    void OpenWebHome();
    void RunPythonCommand(const TCHAR* PythonCode) const;
};
