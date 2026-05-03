#include "MaterialAnalyzerBPLibrary.h"

#include "MaterialAnalyzerExporter.h"

#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Editor/UnrealEd/Public/Selection.h"
#include "Materials/MaterialInterface.h"

FString UMaterialAnalyzerBPLibrary::GetMaterialSummaryJson(const FString& MaterialPath)
{
    UMaterialInterface* MaterialInterface = MaterialAnalyzer::LoadMaterialInterface(MaterialPath);
    if (!MaterialInterface)
    {
        return MaterialAnalyzer::ToJsonString(
            MaterialAnalyzer::MakeError(
                FString::Printf(TEXT("Material not found: %s"), *MaterialPath),
                TEXT("asset_not_found")));
    }

    return MaterialAnalyzer::BuildSummaryJson(MaterialInterface);
}

FString UMaterialAnalyzerBPLibrary::GetSelectedMaterialSummaryJson()
{
    if (!GEditor)
    {
        return MaterialAnalyzer::ToJsonString(
            MaterialAnalyzer::MakeError(TEXT("GEditor is null"), TEXT("editor_unavailable")));
    }

    USelection* Selection = GEditor->GetSelectedObjects();
    if (!Selection)
    {
        return MaterialAnalyzer::ToJsonString(
            MaterialAnalyzer::MakeError(TEXT("Selection is unavailable"), TEXT("selection_unavailable")));
    }

    UMaterialInterface* SelectedMaterial = nullptr;
    for (int32 Index = 0; Index < Selection->Num(); ++Index)
    {
        if (UObject* Obj = Selection->GetSelectedObject(Index))
        {
            SelectedMaterial = Cast<UMaterialInterface>(Obj);
            if (SelectedMaterial)
            {
                break;
            }
        }
    }

    if (!SelectedMaterial)
    {
        return MaterialAnalyzer::ToJsonString(
            MaterialAnalyzer::MakeError(TEXT("No material selected"), TEXT("selection_empty")));
    }

    return MaterialAnalyzer::BuildSummaryJson(SelectedMaterial);
}

FString UMaterialAnalyzerBPLibrary::GetMaterialPropertiesJson(const FString& MaterialPath)
{
    UMaterialInterface* MaterialInterface = MaterialAnalyzer::LoadMaterialInterface(MaterialPath);
    if (!MaterialInterface)
    {
        return MaterialAnalyzer::ToJsonString(
            MaterialAnalyzer::MakeError(TEXT("Material not found"), TEXT("asset_not_found")));
    }

    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("ok"), true);
    Root->SetStringField(TEXT("source"), TEXT("cpp_properties"));
    MaterialAnalyzer::AddMaterialProperties(MaterialInterface, Root);

    return MaterialAnalyzer::ToJsonString(Root);
}

FString UMaterialAnalyzerBPLibrary::GetMaterialShaderCodeJson(const FString& MaterialPath)
{
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("ok"), false);
    Root->SetStringField(TEXT("error_type"), TEXT("not_implemented"));
    Root->SetStringField(TEXT("message"), TEXT("Shader code export is not implemented yet"));
    Root->SetStringField(TEXT("material_path"), MaterialPath);
    return MaterialAnalyzer::ToJsonString(Root);
}

FString UMaterialAnalyzerBPLibrary::CompileMaterialJson(const FString& MaterialPath)
{
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("ok"), false);
    Root->SetStringField(TEXT("error_type"), TEXT("not_implemented"));
    Root->SetStringField(TEXT("message"), TEXT("Compile material endpoint is not implemented yet"));
    Root->SetStringField(TEXT("material_path"), MaterialPath);
    return MaterialAnalyzer::ToJsonString(Root);
}
