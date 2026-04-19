#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "MaterialAnalyzerBPLibrary.generated.h"

UCLASS()
class MATERIALANALYZEREDITOR_API UMaterialAnalyzerBPLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, CallInEditor, Category = "Material Analyzer")
    static FString GetMaterialSummaryJson(const FString& MaterialPath);

    UFUNCTION(BlueprintCallable, CallInEditor, Category = "Material Analyzer")
    static FString GetSelectedMaterialSummaryJson();

    UFUNCTION(BlueprintCallable, CallInEditor, Category = "Material Analyzer")
    static FString GetMaterialPropertiesJson(const FString& MaterialPath);

    UFUNCTION(BlueprintCallable, CallInEditor, Category = "Material Analyzer")
    static FString GetMaterialShaderCodeJson(const FString& MaterialPath);

    UFUNCTION(BlueprintCallable, CallInEditor, Category = "Material Analyzer")
    static FString CompileMaterialJson(const FString& MaterialPath);
};
