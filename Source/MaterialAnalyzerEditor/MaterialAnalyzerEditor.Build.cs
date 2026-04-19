using UnrealBuildTool;

public class MaterialAnalyzerEditor : ModuleRules
{
    public MaterialAnalyzerEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine"
            }
        );

        PrivateDependencyModuleNames.AddRange(
            new[]
            {
                "UnrealEd",
                "Json",
                "JsonUtilities",
                "MaterialEditor",
                "AssetRegistry"
            }
        );
    }
}
