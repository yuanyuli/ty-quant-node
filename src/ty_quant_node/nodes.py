from .engine import train_predict, backtest, save_report
from .data import apply_adjustment
import pandas as pd

class TYQuantAdjustPrices:
    @classmethod
    def INPUT_TYPES(cls): return {"required":{"csv_path":("STRING",{"default":""}),"adjustment":(["qfq","hfq","none"],)}}
    RETURN_TYPES=("STRING",); FUNCTION="run"; CATEGORY="TY Quant/Data"
    def run(self,csv_path,adjustment):
        df=apply_adjustment(pd.read_csv(csv_path), adjustment); out=csv_path.rsplit('.',1)[0]+f"_{adjustment}.csv"; df.to_csv(out,index=False); return (out,)

class TYQuantTrain:
    @classmethod
    def INPUT_TYPES(cls): return {"required":{"csv_path":("STRING",{"default":""}),"adjustment":(["qfq","hfq","none"],)}}
    RETURN_TYPES=("TY_QUANT_RESULT",); FUNCTION="run"; CATEGORY="TY Quant/Model"
    def run(self,csv_path,adjustment): return (train_predict(pd.read_csv(csv_path),adjustment),)

class TYQuantBacktest:
    @classmethod
    def INPUT_TYPES(cls): return {"required":{"result":("TY_QUANT_RESULT",),"topk":("INT",{"default":1,"min":1})}}
    RETURN_TYPES=("STRING","STRING"); FUNCTION="run"; CATEGORY="TY Quant/Backtest"
    def run(self,result,topk):
        m,c=backtest(result,topk); return (str(m), c.to_json(orient="records",date_format="iso"))

class TYQuantReport:
    @classmethod
    def INPUT_TYPES(cls): return {"required":{"result":("TY_QUANT_RESULT",),"output_dir":("STRING",{"default":"outputs/ty_quant"})}}
    RETURN_TYPES=("STRING",); FUNCTION="run"; CATEGORY="TY Quant/Report"
    def run(self,result,output_dir): m,c=backtest(result); return (save_report(m,c,output_dir),)

NODE_CLASS_MAPPINGS={"TYQuantAdjustPrices":TYQuantAdjustPrices,"TYQuantTrain":TYQuantTrain,"TYQuantBacktest":TYQuantBacktest,"TYQuantReport":TYQuantReport}
NODE_DISPLAY_NAME_MAPPINGS={k:k for k in NODE_CLASS_MAPPINGS}
