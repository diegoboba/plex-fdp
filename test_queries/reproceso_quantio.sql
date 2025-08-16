CREATE EXTERNAL TABLE [quantio].[test_bi]
(
    [mes] [date] NULL,
	[emision] [date] NULL,
	[idcomprobante] [int] NULL,
	[idglobal] [int] NULL,
	[orden] [int] NULL,
	[cliapenom] [nvarchar](100) NULL,
	[afilnumero] [nvarchar](20) NULL,
	[afilnombre] [nvarchar](100) NULL,
	[sucursal] [nvarchar](50) NULL,
	[codplex] [bigint] NULL,
	[codebar] [nvarchar](20) NULL,
	[vendedor] [nvarchar](100) NULL,
	[laboratorio] [nvarchar](100) NULL,
	[obrasocial] [nvarchar](25) NULL,
	[plan_os] [nvarchar](100) NULL,
	[unidades] [float] NULL,
	[total] [float] NULL,
	[acosprincipal] [float] NULL,
	[coseguro1] [nvarchar](100) NULL,
	[acoscoseguro1] [float] NULL,
	[coseguro2] [nvarchar](100) NULL,
	[acoscoseguro2] [float] NULL,
	[costoPPP] [float] NULL,
	[ultimocosto] [float] NULL,
	[costo] [float] NULL,
	[IVA] [float] NULL,
	[importeiva] [float] NULL,
	[rn] [bigint] NULL,
	[emision_fecha_hora] [datetime] NULL,
	[producto] [nvarchar](max) NULL,
	[presentaci] [nvarchar](max) NULL
)
WITH (DATA_SOURCE = [remote_plex],SCHEMA_NAME = N'plex',OBJECT_NAME = N'test_bi')
;

select
    t.*,
    f.idcliente

into quantio.reporte_bi

from quantio.test_bi t 
left join quantio.factlineascab f 
    on t.idcomprobante = f.IDComprobante
    and t.orden = f.orden

;
select count(1) from quantio.test_bi
union all 
select count(1) from quantio.reporte_bi

--5452902