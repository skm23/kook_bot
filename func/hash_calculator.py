import hmac
import base64
import loguru
import hashlib
import binascii


class HashCalculator:
    "哈希值计算，多种算法和输出格式"

    #算法
    ALGORITHMS = {
        'md5' : hashlib.md5,
        'sha1' : hashlib.sha1,
        'sha224' : hashlib.sha224,
        'sha256' : hashlib.sha256,
        'sha384' : hashlib.sha384,
        'sha512' : hashlib.sha512,
        'sha3_224' : hashlib.sha3_224,
        'sha3_256' : hashlib.sha3_256,
        'sha3_384' : hashlib.sha3_384,
        'sha3_512' : hashlib.sha3_512,
    }

    def __init__(self):
        self.algorithm = 'md5'
        self.output_format = 'HEX'
        self.output_case = 'upper'
        self.hmac_key = None
        self.separator = ''
        self.encoding = 'utf-8'

    def parse_command(self, command: str) -> dict:
        "解析命令（/hash value ALG alg_name OUT output HMAC key SEP sep COD encoding）"

        parts = command.split()
        if len(parts) < 2 or parts[0] != '/hash':
            return {'error': '命令格式错误，必须以 /hash 开头'}
        
        #数据提取（参数前）
        values = []
        i = 1
        while i < len(parts):
            if parts[i].upper() in ['ALG', 'OUT', 'HMAC', 'SEP', 'COD']:
                break
            values.append(parts[i])
            i += 1

        if not values and i >= len(parts):
            return {'error': '必须提供至少一个要加密的数据或者参数'}
        
        #解析
        params = {'values': values}

        while i < len(parts):
            param = parts[i].upper()

            #检查下一个参数
            if i + 1 >= len(parts):
                if param == 'HMAC':
                    params['hmac_key'] = 'secret'
                i += 1
                continue

            value = parts[i + 1]

            #检查下一个值是否为另一个值
            if value.upper() in ['ALG', 'OUT', 'HMAC', 'SEP', 'COD']:
                # 下一个是参数，当前参数使用默认值
                if param == 'HMAC':
                    params['hmac_key'] = 'secret'
                i += 1
                continue

            #处理数据
            if param == 'ALG':
                if value.lower() in self.ALGORITHMS:
                    params['algorithm'] = value.lower()
                else:
                    return {'error': f'不支持的算法: {value}. 支持的算法: {", ".join(self.ALGORITHMS.keys())}'}
            elif param == 'OUT':
                params['output_format'] = value.upper()
            elif param == 'HMAC':
                params['hmac_key'] = value if value else 'secret'
            elif param == 'SEP':
                params['separator'] = value if value else ''
            elif param == 'COD':
                params['encoding'] = value if value else 'utf-8'

            i += 2

        return params
    
    def calculate_hash(self, data: str, use_hmac: bool = False) -> str:
        "计算哈希值"

        try:
            #根据编码处理数据
            if self.encoding == 'hex':
                data_bytes = bytes.fromhex(data)
            elif self.encoding == 'base64':
                data_bytes = base64.b64decode(data)
            else:
                data_bytes = data.encode(self.encoding)

            #创建哈希对象
            hash_func = self.ALGORITHMS[self.algorithm]

            if use_hmac and self.hmac_key:
                #使用 HMAC
                key_bytes = self.hmac_key.encode(self.encoding)
                h = hmac.new(key_bytes, data_bytes, hash_func)
            else:
                #普通
                h = hash_func(data_bytes)

            #获取哈希结果
            hash_result = h.digest()

            #处理格式
            if self.output_format == 'BASE64':
                result = base64.b64encode(hash_result).decode('ascii')
            else:
                #HEX
                result = binascii.hexlify(hash_result).decode('ascii')

            #处理大小写
            if self.output_case == 'lower' and self.output_format == 'HEX':
                result = result.lower()
            elif self.output_case == 'upper' and self.output_format == 'HEX':
                result = result.upper()

            return result
        
        except Exception as e:
            loguru.logger.warning("处理 /hash 命令时出错: {e}")
            return f'计算错误: {str(e)}'
        
    def process_command(self, command: str) -> str:
        "哈希计算"

        #解析
        params = self.parse_command(command)
        if 'error' in params:
            return params['error']
        
        #设置参数
        self.algorithm = params.get('algorithm', 'md5')
        output_format = params.get('output_format', 'HEX')
        self.output_format = output_format
        self.output_case = 'upper'
        self.hmac_key = params.get('hmac_key', None)
        self.separator = params.get('separator', '')
        self.encoding = params.get('encoding', 'utf-8')

        #处理输出
        if output_format.upper() == 'BASE64':
            self.output_format = 'BASE64'
        elif output_format.upper() == 'HEX':
            self.output_format = 'HEX'
        elif output_format.upper() == 'LOWER':
            self.output_format = 'HEX'
            self.output_case = 'lower'
        elif output_format.upper() == 'UPPER':
            self.output_format = 'HEX'
            self.output_case = 'upper'

        #计算哈希值
        results = []
        use_hmac = self.hmac_key is not None

        for Value in params['values']:
            result = self.calculate_hash(Value, use_hmac)
            results.append(result)

        #分隔符
        final_result = self.separator.join(results)

        #返回格式结果
        output = []
        output.append(f"算法: {self.algorithm.upper()}")
        if use_hmac:
            output.append(f"HMAC密钥: {self.hmac_key}")
        output.append(f"输出格式: {self.output_format}")
        if self.output_format == 'HEX':
            output.append(f"大小写: {self.output_case}")
        output.append(f"编码: {self.encoding}")
        if self.separator:
            output.append(f"分隔符: {repr(self.separator)}")
        output.append(f"\n结果: {final_result}")

        return '\n'.join(output)
    
calculator = HashCalculator()
            
