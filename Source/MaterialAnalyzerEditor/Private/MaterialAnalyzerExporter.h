#pragma once

#include "CoreMinimal.h"

class UMaterialInterface;
class FJsonObject;

namespace MaterialAnalyzer
{
    FString ToJsonString(const TSharedRef<FJsonObject>& JsonObject);

    TSharedRef<FJsonObject> MakeError(const FString& Message, const FString& ErrorType = TEXT("unknown"));

    UMaterialInterface* LoadMaterialInterface(const FString& MaterialPath);

    void AddMaterialProperties(UMaterialInterface* MaterialInterface, const TSharedRef<FJsonObject>& Root);

    FString BuildSummaryJson(UMaterialInterface* MaterialInterface);
}