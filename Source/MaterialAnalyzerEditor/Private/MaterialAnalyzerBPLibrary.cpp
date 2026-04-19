#include "MaterialAnalyzerBPLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Editor/UnrealEd/Public/Selection.h"
#include "JsonObjectConverter.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpression.h"
#include "Materials/MaterialExpressionComment.h"
#include "Materials/MaterialExpressionParameter.h"
#include "Materials/MaterialInterface.h"
#include "MaterialEditingLibrary.h"
#include "MaterialShader.h"
#include "Misc/EngineVersion.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace MaterialAnalyzer
{
    static FString ToJsonString(const TSharedRef<FJsonObject>& JsonObject)
    {
        FString JsonString;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonString);
        FJsonSerializer::Serialize(JsonObject, Writer);
        return JsonString;
    }

    static TSharedRef<FJsonObject> MakeError(const FString& Message, const FString& ErrorType = TEXT("unknown"))
    {
        TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
        Root->SetBoolField(TEXT("ok"), false);
        Root->SetStringField(TEXT("error_type"), ErrorType);
        Root->SetStringField(TEXT("message"), Message);
        return Root;
    }

    static UMaterialInterface* LoadMaterialInterface(const FString& MaterialPath)
    {
        UObject* Asset = StaticLoadObject(UObject::StaticClass(), nullptr, *MaterialPath);
        return Cast<UMaterialInterface>(Asset);
    }

    static FString GetExpressionNodeId(const UMaterialExpression* Expression)
    {
        if (!Expression)
        {
            return TEXT("");
        }

        return Expression->GetName();
    }

    static TArray<UMaterialExpression*> GetExpressions(UMaterial* Material)
    {
        if (!Material)
        {
            return {};
        }

        TArray<UMaterialExpression*> Result;
        TSet<UMaterialExpression*> SeenExpressions;

        auto AddExpression = [&Result, &SeenExpressions](UMaterialExpression* Expr)
        {
            if (!Expr || Expr->IsA<UMaterialExpressionComment>() || SeenExpressions.Contains(Expr))
            {
                return;
            }

            SeenExpressions.Add(Expr);
            Result.Add(Expr);
        };

        for (const TObjectPtr<UMaterialExpression>& Expr : Material->GetExpressions())
        {
            AddExpression(Expr.Get());
        }

        TArray<UMaterialExpression*> ReferencedExpressions;
        if (Material->GetAllReferencedExpressions(
                ReferencedExpressions,
                nullptr,
                ERHIFeatureLevel::Num,
                EMaterialQualityLevel::Num,
                ERHIShadingPath::Num,
                true))
        {
            for (UMaterialExpression* Expr : ReferencedExpressions)
            {
                AddExpression(Expr);
            }
        }

        if (Result.Num() == 0)
        {
            const FMaterialExpressionCollection& Collection = Material->GetExpressionCollection();
            for (const TObjectPtr<UMaterialExpression>& Expr : Collection.Expressions)
            {
                AddExpression(Expr.Get());
            }
        }
        return Result;
    }

    static void AddMaterialProperties(UMaterialInterface* MaterialInterface, const TSharedRef<FJsonObject>& Root)
    {
        TSharedRef<FJsonObject> MaterialJson = MakeShared<FJsonObject>();
        MaterialJson->SetStringField(TEXT("path"), MaterialInterface ? MaterialInterface->GetPathName() : TEXT(""));
        MaterialJson->SetStringField(TEXT("name"), MaterialInterface ? MaterialInterface->GetName() : TEXT(""));

        UMaterial* BaseMaterial = MaterialInterface ? MaterialInterface->GetMaterial() : nullptr;
        if (BaseMaterial)
        {
            MaterialJson->SetStringField(TEXT("domain"), StaticEnum<EMaterialDomain>()->GetNameStringByValue((int64)BaseMaterial->MaterialDomain));
            MaterialJson->SetStringField(TEXT("blend_mode"), StaticEnum<EBlendMode>()->GetNameStringByValue((int64)BaseMaterial->BlendMode));
            MaterialJson->SetStringField(TEXT("shading_model"), GetShadingModelFieldString(BaseMaterial->GetShadingModels()));
            MaterialJson->SetBoolField(TEXT("two_sided"), BaseMaterial->TwoSided);
        }

        Root->SetObjectField(TEXT("material"), MaterialJson);
    }

    static TArray<TSharedPtr<FJsonValue>> BuildNodes(UMaterial* Material, TMap<const UMaterialExpression*, FString>& OutIdMap)
    {
        TArray<TSharedPtr<FJsonValue>> Nodes;
        TArray<UMaterialExpression*> Expressions = GetExpressions(Material);

        for (UMaterialExpression* Expr : Expressions)
        {
            if (!Expr)
            {
                continue;
            }

            const FString NodeId = GetExpressionNodeId(Expr);
            OutIdMap.Add(Expr, NodeId);

            TSharedRef<FJsonObject> NodeJson = MakeShared<FJsonObject>();
            NodeJson->SetStringField(TEXT("id"), NodeId);
            NodeJson->SetStringField(TEXT("name"), Expr->GetName());
            NodeJson->SetStringField(TEXT("class"), Expr->GetClass()->GetName());
            NodeJson->SetStringField(TEXT("desc"), Expr->Desc);
            NodeJson->SetNumberField(TEXT("editor_x"), Expr->MaterialExpressionEditorX);
            NodeJson->SetNumberField(TEXT("editor_y"), Expr->MaterialExpressionEditorY);

            if (const UMaterialExpressionParameter* ParamExpr = Cast<UMaterialExpressionParameter>(Expr))
            {
                NodeJson->SetBoolField(TEXT("is_parameter"), true);
                NodeJson->SetStringField(TEXT("parameter_name"), ParamExpr->ParameterName.ToString());
            }
            else
            {
                NodeJson->SetBoolField(TEXT("is_parameter"), false);
                NodeJson->SetStringField(TEXT("parameter_name"), TEXT(""));
            }

            TArray<TSharedPtr<FJsonValue>> InputPins;
            for (int32 InputIndex = 0;; ++InputIndex)
            {
                const FExpressionInput* Input = Expr->GetInput(InputIndex);
                if (!Input)
                {
                    break;
                }

                TSharedRef<FJsonObject> InputPin = MakeShared<FJsonObject>();
                InputPin->SetNumberField(TEXT("index"), InputIndex);
                InputPin->SetStringField(TEXT("name"), Expr->GetInputName(InputIndex).ToString());
                InputPins.Add(MakeShared<FJsonValueObject>(InputPin));
            }
            NodeJson->SetArrayField(TEXT("input_pins"), InputPins);

            TArray<TSharedPtr<FJsonValue>> OutputPins;
            TArray<FExpressionOutput>& Outputs = Expr->GetOutputs();
            for (int32 OutputIndex = 0; OutputIndex < Outputs.Num(); ++OutputIndex)
            {
                TSharedRef<FJsonObject> OutputPin = MakeShared<FJsonObject>();
                OutputPin->SetNumberField(TEXT("index"), OutputIndex);
                OutputPin->SetStringField(TEXT("name"), Outputs[OutputIndex].OutputName.ToString());
                OutputPins.Add(MakeShared<FJsonValueObject>(OutputPin));
            }
            NodeJson->SetArrayField(TEXT("output_pins"), OutputPins);

            Nodes.Add(MakeShared<FJsonValueObject>(NodeJson));
        }

        return Nodes;
    }

    static TArray<TSharedPtr<FJsonValue>> BuildEdges(
        UMaterial* Material,
        const TMap<const UMaterialExpression*, FString>& IdMap)
    {
        TArray<TSharedPtr<FJsonValue>> Edges;
        TSet<FString> EdgeDedup;
        TArray<UMaterialExpression*> Expressions = GetExpressions(Material);

        for (UMaterialExpression* Expr : Expressions)
        {
            if (!Expr)
            {
                continue;
            }

            const FString* ToNodeId = IdMap.Find(Expr);
            if (!ToNodeId)
            {
                continue;
            }

            for (FExpressionInputIterator It{Expr}; It; ++It)
            {
                const FExpressionInput* Input = It.Input;
                if (!Input || !Input->Expression)
                {
                    continue;
                }

                const FString* FromNodeId = IdMap.Find(Input->Expression);
                if (!FromNodeId)
                {
                    continue;
                }

                const FString ToPin = Expr->GetInputName(It.Index).ToString();
                const FString DedupKey = *FromNodeId + TEXT("->") + *ToNodeId + TEXT(":") + ToPin;
                if (EdgeDedup.Contains(DedupKey))
                {
                    continue;
                }
                EdgeDedup.Add(DedupKey);

                FString FromPinName = TEXT("Output");
                if (Input->OutputIndex != INDEX_NONE)
                {
                    UMaterialExpression* SourceExpr = Input->Expression;
                    if (SourceExpr)
                    {
                        const FExpressionOutput* SourceOutput = SourceExpr->GetOutput(Input->OutputIndex);
                        if (SourceOutput && !SourceOutput->OutputName.IsNone())
                        {
                            FromPinName = SourceOutput->OutputName.ToString();
                        }
                    }
                }

                TSharedRef<FJsonObject> EdgeJson = MakeShared<FJsonObject>();
                EdgeJson->SetStringField(TEXT("from_node_id"), *FromNodeId);
                EdgeJson->SetStringField(TEXT("from_pin"), FromPinName);
                EdgeJson->SetNumberField(TEXT("from_output_index"), Input->OutputIndex);
                EdgeJson->SetStringField(TEXT("to_node_id"), *ToNodeId);
                EdgeJson->SetStringField(TEXT("to_pin"), ToPin);
                Edges.Add(MakeShared<FJsonValueObject>(EdgeJson));
            }
        }

        return Edges;
    }

    static TArray<TSharedPtr<FJsonValue>> BuildPropertyBindings(
        UMaterial* Material,
        const TMap<const UMaterialExpression*, FString>& IdMap)
    {
        TArray<TSharedPtr<FJsonValue>> Bindings;

        struct FPropertyPair
        {
            EMaterialProperty Property;
            const TCHAR* Name;
        };

        const FPropertyPair Pairs[] = {
            {MP_BaseColor, TEXT("BaseColor")},
            {MP_EmissiveColor, TEXT("EmissiveColor")},
            {MP_Opacity, TEXT("Opacity")},
            {MP_OpacityMask, TEXT("OpacityMask")},
            {MP_Normal, TEXT("Normal")},
            {MP_Roughness, TEXT("Roughness")},
            {MP_Metallic, TEXT("Metallic")},
            {MP_Specular, TEXT("Specular")},
            {MP_AmbientOcclusion, TEXT("AmbientOcclusion")},
        };

        for (const FPropertyPair& Pair : Pairs)
        {
            UMaterialExpression* Expr = UMaterialEditingLibrary::GetMaterialPropertyInputNode(Material, Pair.Property);
            if (!Expr)
            {
                continue;
            }

            const FString* NodeId = IdMap.Find(Expr);
            if (!NodeId)
            {
                continue;
            }

            TSharedRef<FJsonObject> BindingJson = MakeShared<FJsonObject>();
            BindingJson->SetStringField(TEXT("property_name"), Pair.Name);
            BindingJson->SetStringField(TEXT("node_id"), *NodeId);
            BindingJson->SetStringField(TEXT("pin_name"), TEXT("Output"));
            Bindings.Add(MakeShared<FJsonValueObject>(BindingJson));
        }

        return Bindings;
    }

    static TArray<TSharedPtr<FJsonValue>> BuildComments(UMaterial* Material)
    {
        TArray<TSharedPtr<FJsonValue>> Comments;
        if (!Material)
        {
            return Comments;
        }

        const TArray<TObjectPtr<UMaterialExpressionComment>>& EditorComments = Material->GetExpressionCollection().EditorComments;
        for (const TObjectPtr<UMaterialExpressionComment>& Comment : EditorComments)
        {
            if (!Comment)
            {
                continue;
            }

            TSharedRef<FJsonObject> CommentJson = MakeShared<FJsonObject>();
            CommentJson->SetStringField(TEXT("text"), Comment->Text);
            CommentJson->SetNumberField(TEXT("editor_x"), Comment->MaterialExpressionEditorX);
            CommentJson->SetNumberField(TEXT("editor_y"), Comment->MaterialExpressionEditorY);
            CommentJson->SetNumberField(TEXT("size_x"), Comment->SizeX);
            CommentJson->SetNumberField(TEXT("size_y"), Comment->SizeY);
            Comments.Add(MakeShared<FJsonValueObject>(CommentJson));
        }

        return Comments;
    }

    static FString BuildSummaryJson(UMaterialInterface* MaterialInterface)
    {
        if (!MaterialInterface)
        {
            return ToJsonString(MakeError(TEXT("MaterialInterface is null"), TEXT("asset_not_found")));
        }

        UMaterial* BaseMaterial = MaterialInterface->GetMaterial();
        if (!BaseMaterial)
        {
            return ToJsonString(MakeError(TEXT("Failed to resolve base material"), TEXT("material_not_resolved")));
        }

        TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
        Root->SetBoolField(TEXT("ok"), true);
        Root->SetStringField(TEXT("source"), TEXT("cpp_graph"));
        Root->SetStringField(TEXT("source_type"), TEXT("cpp_graph"));
        Root->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());

        AddMaterialProperties(MaterialInterface, Root);

        TMap<const UMaterialExpression*, FString> IdMap;
        TArray<TSharedPtr<FJsonValue>> Nodes = BuildNodes(BaseMaterial, IdMap);
        TArray<TSharedPtr<FJsonValue>> Edges = BuildEdges(BaseMaterial, IdMap);
        TArray<TSharedPtr<FJsonValue>> PropertyBindings = BuildPropertyBindings(BaseMaterial, IdMap);
        TArray<TSharedPtr<FJsonValue>> Comments = BuildComments(BaseMaterial);

        Root->SetArrayField(TEXT("nodes"), Nodes);
        Root->SetArrayField(TEXT("edges"), Edges);
        Root->SetArrayField(TEXT("property_bindings"), PropertyBindings);
        Root->SetArrayField(TEXT("comments"), Comments);

        TSharedRef<FJsonObject> Stats = MakeShared<FJsonObject>();
        Stats->SetNumberField(TEXT("node_count"), Nodes.Num());
        Stats->SetNumberField(TEXT("edge_count"), Edges.Num());
        Stats->SetNumberField(TEXT("binding_count"), PropertyBindings.Num());
        Stats->SetNumberField(TEXT("comment_count"), Comments.Num());
        Root->SetObjectField(TEXT("stats"), Stats);

        TSharedRef<FJsonObject> Meta = MakeShared<FJsonObject>();
        Meta->SetStringField(TEXT("material_path"), MaterialInterface->GetPathName());
        Meta->SetStringField(TEXT("material_name"), MaterialInterface->GetName());
        Root->SetObjectField(TEXT("meta"), Meta);

        return ToJsonString(Root);
    }
}

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
