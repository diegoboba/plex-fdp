drop external table plex.reporte_bi;

CREATE EXTERNAL TABLE [plex].[reporte_bi]
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
	[presentaci] [nvarchar](max) NULL,
	[idcliente] [bigint] NULL
)
WITH (DATA_SOURCE = [remote_quantio],SCHEMA_NAME = N'quantio',OBJECT_NAME = N'reporte_bi')
;

select 
	r.*
into plex.test_bi 
from plex.reporte_bi r 