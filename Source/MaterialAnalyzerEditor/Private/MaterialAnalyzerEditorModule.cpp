#include "MaterialAnalyzerEditorModule.h"

#include "Engine/Engine.h"
#include "Modules/ModuleManager.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "FMaterialAnalyzerEditorModule"

IMPLEMENT_MODULE(FMaterialAnalyzerEditorModule, MaterialAnalyzerEditor)

void FMaterialAnalyzerEditorModule::StartupModule()
{
	UToolMenus::RegisterStartupCallback(
		FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FMaterialAnalyzerEditorModule::RegisterMenus));
}

void FMaterialAnalyzerEditorModule::ShutdownModule()
{
	UToolMenus::UnRegisterStartupCallback(this);
	UToolMenus::UnregisterOwner(this);
}

void FMaterialAnalyzerEditorModule::RegisterMenus()
{
	FToolMenuOwnerScoped OwnerScoped(this);

	UToolMenu* WindowMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
	FToolMenuSection& Section = WindowMenu->FindOrAddSection("WindowLayout");

	Section.AddMenuEntry(
		"MaterialAnalyzerOpenWebHome",
		LOCTEXT("MaterialAnalyzerMenuEntry", "Material Analyzer"),
		LOCTEXT("MaterialAnalyzerMenuEntryTooltip", "Open the Material Analyzer web app home page."),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FMaterialAnalyzerEditorModule::OpenWebHome)));
}

void FMaterialAnalyzerEditorModule::OpenWebHome()
{
	RunPythonCommand(TEXT("import ue_open_web_for_selected_material as launcher; launcher.open_web_home()"));
}

void FMaterialAnalyzerEditorModule::RunPythonCommand(const TCHAR* PythonCode) const
{
	if (!GEngine)
	{
		return;
	}

	const FString Command = FString::Printf(TEXT("py %s"), PythonCode);
	GEngine->Exec(nullptr, *Command);
}

#undef LOCTEXT_NAMESPACE
